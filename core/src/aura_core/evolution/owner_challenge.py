"""Trusted owner-control-plane WebAuthn challenge and approval lifecycle.

This is a server-side *library*, not a route exposed by AURA Core. A separate
authenticated, owner-protected service must exclusively own its database,
passkey credential, approval store and allowed origin. AURA's bearer token is
not a substitute for physical owner identity.
"""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from typing import Any
from uuid import uuid4

from aura_core.enterprise.approval_store import (
    ApprovalStatus, SQLiteApprovalStore,
)
from aura_core.evolution.owner_passkey import OwnerPasskeyVerifier, WebAuthnOwnerAssertion


class TrustedOwnerPasskeyDecider:
    """Persistent one-shot challenge + counter; approve only after valid UV proof."""

    def __init__(
        self, *, database_path: str | Path,
        owner_verifier: OwnerPasskeyVerifier,
        approvals: SQLiteApprovalStore,
        policy_digest: str,
        credential_id: str,
        ttl_seconds: int = 90,
    ) -> None:
        path = Path(database_path)
        if not path.is_absolute() or not path.is_file() or path.is_symlink():
            raise ValueError("Pre-provisioned absolute trusted challenge DB required")
        if path.resolve().is_relative_to(Path(__file__).resolve().parents[4]):
            raise PermissionError("Owner approval DB must live outside AURA checkout")
        if os.name == "posix" and path.stat().st_mode & 0o077:
            raise PermissionError("Challenge store must be owner-only")
        if not isinstance(owner_verifier, OwnerPasskeyVerifier) or not isinstance(approvals, SQLiteApprovalStore):
            raise ValueError("Trusted owner verifier and store required")
        if not isinstance(policy_digest, str) or len(policy_digest) != 64 or any(c not in "0123456789abcdef" for c in policy_digest):
            raise ValueError("Pinned local owner policy digest required")
        if not isinstance(credential_id, str) or len(credential_id) > 512:
            raise ValueError("Credential identity required")
        if type(ttl_seconds) is not int or not 10 <= ttl_seconds <= 120:
            raise ValueError("Challenge expiry must be 10..120 seconds")
        self._auth = owner_verifier
        self._approvals = approvals
        self._policy = policy_digest
        self._credential_id = credential_id
        self._ttl = ttl_seconds
        self._db = sqlite3.connect(str(path), isolation_level=None, timeout=5, check_same_thread=False)
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.execute("PRAGMA journal_mode=DELETE")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS owner_passkey_challenges (
                challenge_id TEXT PRIMARY KEY,
                approval_id TEXT NOT NULL,
                approval_version INTEGER NOT NULL,
                fingerprint TEXT NOT NULL,
                challenge BLOB NOT NULL,
                expires_at INTEGER NOT NULL,
                used INTEGER NOT NULL DEFAULT 0
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS owner_passkey_state (
                slot TEXT PRIMARY KEY CHECK(slot='owner'),
                sign_count INTEGER NOT NULL CHECK(sign_count >= 0)
            )
        """)
        self._db.execute("INSERT OR IGNORE INTO owner_passkey_state(slot, sign_count) VALUES ('owner', 0)")
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "TrustedOwnerPasskeyDecider":
        return self

    def __exit__(self, exc: Any, val: Any, tb: Any) -> None:
        self.close()

    def _record(self, approval_id: str):
        record = self._approvals.get(approval_id)
        if (record is None or record.status is not ApprovalStatus.PENDING
                or record.capability_id != "GovernedSkillActivation"
                or record.principal_id != "local_owner"
                or record.policy_digest != self._policy
                or record.operation_id not in {"activate", "rollback", "revoke"}
                or record.resource_scope != "evolution:skill:" + record.request_fingerprint):
            raise PermissionError("Not an eligible owner-governed pending approval")
        return record

    def issue(self, approval_id: str) -> dict[str, object]:
        if not isinstance(approval_id, str) or not 1 <= len(approval_id) <= 128:
            raise ValueError("Approval identifier invalid")
        record = self._record(approval_id)
        challenge = secrets.token_bytes(32)
        challenge_id = str(uuid4())
        expires = int(time.time()) + self._ttl
        with self._lock:
            self._db.execute(
                "INSERT INTO owner_passkey_challenges "
                "(challenge_id, approval_id, approval_version, fingerprint, challenge, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (challenge_id, approval_id, record.version, record.request_fingerprint, challenge, expires),
            )
        return {
            "challenge_id": challenge_id,
            "challenge": base64.urlsafe_b64encode(challenge).decode().rstrip("="),
            "credential_id": self._credential_id,
            "rp_id": "localhost",
            "user_verification": "required",
            "timeout_ms": self._ttl * 1000,
            "expires_at": expires,
        }

    def decide(self, *, challenge_id: str, assertion: WebAuthnOwnerAssertion,
               decision: ApprovalStatus = ApprovalStatus.APPROVED):
        if decision not in {ApprovalStatus.APPROVED, ApprovalStatus.DENIED}:
            raise ValueError("Only approved/denied owner decisions supported")
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute(
                    "SELECT approval_id, approval_version, fingerprint, challenge, expires_at, used "
                    "FROM owner_passkey_challenges WHERE challenge_id=?",
                    (challenge_id,),
                ).fetchone()
                if row is None or row[5] != 0 or int(time.time()) >= row[4]:
                    raise PermissionError("Owner challenge expired, consumed or unknown")
                record = self._record(row[0])
                if record.version != row[1] or record.request_fingerprint != row[2]:
                    raise PermissionError("Approval changed after challenge issuance")
                count = self._db.execute(
                    "SELECT sign_count FROM owner_passkey_state WHERE slot='owner'",
                ).fetchone()[0]
                new_count = self._auth.verify(
                    assertion, expected_challenge=row[3], previous_counter=count,
                )
                self._db.execute(
                    "UPDATE owner_passkey_challenges SET used=1 WHERE challenge_id=? AND used=0",
                    (challenge_id,),
                )
                self._db.execute("UPDATE owner_passkey_state SET sign_count=? WHERE slot='owner'",
                                 (new_count,))
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        # Challenge is now durable/consumed. If approval-store decision fails,
        # the owner can issue a NEW challenge. Never restore used proof.
        return self._approvals.decide(
            row[0], expected_version=row[1], approver_id="human:local-owner",
            decision=decision,
        )
