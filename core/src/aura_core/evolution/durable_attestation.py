"""Durable, atomic attestation replay ledger for a trusted owner control plane.

Unlike the prototype in-memory registry, evidence survives process restarts.
The SQLite database MUST be provisioned outside the AURA checkout and writable
only by an independently isolated attestor/control-plane OS identity. Sharing
the AURA Core process/user with this store is NOT a hardened trust boundary.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any

from aura_core.evolution.sandbox_attestor import (
    DOMAIN, IndependentAttestationVerifier, SignedSandboxAttestation,
)


class DurableAttestationReceiptRegistry:
    def __init__(
        self, *, database_path: str | Path,
        verifier: IndependentAttestationVerifier,
        max_receipts: int = 4096,
    ) -> None:
        if not isinstance(verifier, IndependentAttestationVerifier):
            raise ValueError("Independent verifier required")
        if not isinstance(max_receipts, int) or isinstance(max_receipts, bool) or not 1 <= max_receipts <= 1_000_000:
            raise ValueError("Invalid bounded receipt capacity")
        path = Path(database_path)
        if not path.is_absolute() or str(path) == ":memory:" or path.is_symlink():
            raise ValueError("A pre-provisioned, absolute, non-symlink database is required")
        if not path.parent.is_dir() or path.parent.is_symlink():
            raise ValueError("Trusted replay storage directory must already exist")
        if not path.exists():
            raise FileNotFoundError("Trusted replay database must be provisioned by the owner")
        if not path.is_file():
            raise ValueError("Replay storage must be a regular file")
        root = Path(__file__).resolve().parents[4]
        if path.resolve().is_relative_to(root):
            raise PermissionError("Trusted replay DB must live outside AURA checkout")
        # Reject world/group access where portable POSIX ownership is meaningful.
        if os.name == "posix" and (path.stat().st_mode & 0o077):
            raise PermissionError("Trusted replay DB must have owner-only permissions")
        self._path = path
        self._verifier = verifier
        self._max = max_receipts
        self._lock = threading.RLock()
        self._db = sqlite3.connect(
            str(path), timeout=5, isolation_level=None, check_same_thread=False,
        )
        try:
            self._db.execute("PRAGMA busy_timeout=5000")
            self._db.execute("PRAGMA journal_mode=DELETE")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS attestation_receipts (
                    receipt TEXT PRIMARY KEY,
                    key_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    envelope TEXT NOT NULL,
                    UNIQUE(key_id, run_id)
                )
            """)
        except Exception:
            self._db.close()
            raise

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "DurableAttestationReceiptRegistry":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def register(
        self, envelope: SignedSandboxAttestation, *,
        source_sha256: str, binding_digest: str, now: int | None = None,
    ) -> str:
        if not self._verifier.verify(
            envelope, source_sha256=source_sha256, binding_digest=binding_digest,
            now=now,
        ):
            raise PermissionError("Untrusted independent sandbox attestation")
        record = json.dumps(envelope.to_dict(), sort_keys=True, separators=(",", ":"))
        receipt = hashlib.sha256(DOMAIN + record.encode("ascii")).hexdigest()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                count = self._db.execute("SELECT COUNT(*) FROM attestation_receipts").fetchone()[0]
                if count >= self._max:
                    raise PermissionError("Replay ledger at capacity; fail closed")
                self._db.execute(
                    "INSERT INTO attestation_receipts (receipt, key_id, run_id, envelope) VALUES (?, ?, ?, ?)",
                    (receipt, envelope.key_id, envelope.claims.run_id, record),
                )
                self._db.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                self._db.execute("ROLLBACK")
                raise PermissionError("Repeated attestor run ID or evidence receipt") from exc
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        return receipt

    def verify_binding(self, binding: object, receipt: str) -> bool:
        if not isinstance(receipt, str) or len(receipt) != 64:
            return False
        try:
            with self._lock:
                row = self._db.execute(
                    "SELECT envelope FROM attestation_receipts WHERE receipt=?",
                    (receipt,),
                ).fetchone()
            if row is None:
                return False
            value = SignedSandboxAttestation.from_dict(json.loads(row[0]))
            canonical = json.dumps(value.to_dict(), sort_keys=True, separators=(",", ":"))
            if hashlib.sha256(DOMAIN + canonical.encode("ascii")).hexdigest() != receipt:
                return False
            return self._verifier.verify(
                value, source_sha256=getattr(binding, "source_sha256", None),
                binding_digest=getattr(binding, "review_digest", None),
            )
        except (sqlite3.Error, ValueError, TypeError, KeyError):
            return False
