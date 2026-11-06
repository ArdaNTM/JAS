"""Broker nonce persistence and separately authenticated measurement envelopes.

These are building blocks, NOT authorization to sign a host isolation receipt.
Signer keys are independently provisioned outside the repo, never generated here.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

from .audit_broker_protocol import BrokerDenied

MEASUREMENT_DOMAIN = b"AURA:OSWORLD:DOCKER-BROKER-MEASUREMENT:v1\n"
SCHEMA = "aura.osworld.docker-broker-measurement.v1"
_HEX32 = re.compile(r"[0-9a-f]{32}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")



def _verify_private_state_path(path: Path) -> None:
    """Fail closed on Windows: broker-owned D: state directory with private ACL."""
    if os.name != "nt":
        return
    if path.drive.upper() != "D:":
        raise BrokerDenied("Broker state must reside on D:")
    from aura_core.evolution.windows_owner_storage import require_private_acl
    require_private_acl(path.parent)
    if path.exists():
        require_private_acl(path)



def _harden_state_file(path: Path) -> None:
    if os.name != "nt":
        return
    from aura_core.evolution.windows_owner_storage import (
        harden_private_acl, require_private_acl,
    )
    harden_private_acl(path)
    require_private_acl(path)


class DurableNonceStore:
    """SQLite PRIMARY KEY replay store; BEGIN IMMEDIATE claims atomically.

    The directory must already exist and be privately ACL-protected. SQLite
    uses DELETE journal to avoid persistent WAL sidecar artifacts.
    """

    def __init__(self, path: Path):
        if not isinstance(path, Path) or not path.is_absolute():
            raise BrokerDenied("Nonce store requires absolute path")
        if path.is_symlink() or not path.parent.is_dir() or path.parent.is_symlink():
            raise BrokerDenied("Nonce store directory not safely provisioned")
        _verify_private_state_path(path)
        self.path = path
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS consumed_nonces (
                    nonce TEXT PRIMARY KEY NOT NULL,
                    expires_at INTEGER NOT NULL
                )
            """)
        _harden_state_file(path)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(
            self.path, timeout=2.0, isolation_level=None,
        )
        db.execute("PRAGMA busy_timeout=2000")
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def claim(self, nonce: str, *, now: int | None = None) -> bool:
        if type(nonce) is not str or not _HEX32.fullmatch(nonce):
            raise BrokerDenied("Invalid nonce")
        if now is None:
            now = int(time.time())
        if type(now) is not int:
            raise BrokerDenied("Invalid trusted clock")
        with self._connect() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "DELETE FROM consumed_nonces WHERE expires_at < ?",
                    (now - 300,),
                )
                cursor = db.execute(
                    "INSERT OR IGNORE INTO consumed_nonces (nonce, expires_at) "
                    "VALUES (?, ?)",
                    (nonce, now + 600),
                )
                inserted = cursor.rowcount == 1
                db.execute("COMMIT")
                return inserted
            except Exception:
                db.execute("ROLLBACK")
                raise


def _claims(obj: object) -> dict[str, object]:
    """Exact schema and true-positive checks, before key verification."""
    fields = {
        "schema", "run_id", "container_id", "nonce", "checked_at",
        "boot", "host_ports", "checks",
    }
    if type(obj) is not dict or set(obj) != fields or obj["schema"] != SCHEMA:
        raise BrokerDenied("Unexpected broker measurement schema")
    for key, pat in (("run_id", _HEX32), ("container_id", _HEX64), ("nonce", _HEX32)):
        if type(obj[key]) is not str or not pat.fullmatch(obj[key]):
            raise BrokerDenied("Malformed broker measurement identity")
    if type(obj["checked_at"]) is not int:
        raise BrokerDenied("Invalid broker measurement timestamp")
    from .isolation import BootIdentity, REQUIRED_CHECKS, EXPECTED_PORTS
    boot = obj["boot"]
    if type(boot) is not dict or set(boot) != {
        "container_id", "network_id", "vm_sha256", "image",
        "gateway_container_id", "gateway_network_id",
    }:
        raise BrokerDenied("Malformed broker boot identity")
    verified = BootIdentity(**boot)
    if verified.container_id != obj["container_id"]:
        raise BrokerDenied("Broker boot/container mismatch")
    checks = obj["checks"]
    if type(checks) is not dict or set(checks) != REQUIRED_CHECKS or not all(
        value is True for value in checks.values()
    ):
        raise BrokerDenied("Broker did not pass every negative probe")
    ports = obj["host_ports"]
    if type(ports) is not dict or set(ports) != {str(p) for p in EXPECTED_PORTS}:
        raise BrokerDenied("Broker host port inventory mismatch")
    for value in ports.values():
        if (type(value) is not str
                or not re.fullmatch(r"127\.0\.0\.1:[1-9][0-9]{0,4}", value)
                or int(value.rsplit(":", 1)[1]) > 65535):
            raise BrokerDenied("Broker exposes a non-loopback port")
    return obj


def signing_bytes(claims: dict[str, object]) -> bytes:
    _claims(claims)
    return MEASUREMENT_DOMAIN + json.dumps(
        claims, sort_keys=True, separators=(",", ":"),
        allow_nan=False, ensure_ascii=True,
    ).encode("ascii")


def sign_measurement(
    claims: dict[str, object], *, signer: Ed25519PrivateKey,
) -> dict[str, object]:
    if not isinstance(signer, Ed25519PrivateKey):
        raise BrokerDenied("Broker requires separate Ed25519 service key")
    sig = signer.sign(signing_bytes(claims))
    return {**claims, "signature_b64": base64.b64encode(sig).decode("ascii")}


def verify_measurement(
    envelope: object,
    *,
    pinned_public_key: bytes,
    expected_nonce: str,
    expected_container_id: str,
    expected_run_id: str,
    now: int | None = None,
) -> dict[str, object]:
    if type(envelope) is not dict or "signature_b64" not in envelope:
        raise BrokerDenied("Missing signed broker measurement")
    claims = {k: v for k, v in envelope.items() if k != "signature_b64"}
    if len(envelope) != len(claims) + 1:
        raise BrokerDenied("Malformed broker envelope")
    data = signing_bytes(claims)
    if (claims["nonce"] != expected_nonce
            or claims["container_id"] != expected_container_id
            or claims["run_id"] != expected_run_id):
        raise BrokerDenied("Broker evidence is bound to another request")
    current = int(time.time()) if now is None else now
    if type(current) is not int or not current - 30 <= claims["checked_at"] <= current + 5:
        raise BrokerDenied("Broker measurement is stale")
    if type(pinned_public_key) is not bytes or len(pinned_public_key) != 32:
        raise BrokerDenied("Broker public key must be independently pinned")
    sig_b64 = envelope["signature_b64"]
    if type(sig_b64) is not str:
        raise BrokerDenied("Malformed broker signature")
    try:
        sig = base64.b64decode(sig_b64, validate=True)
        if len(sig) != 64:
            raise BrokerDenied("Invalid broker signature length")
        Ed25519PublicKey.from_public_bytes(pinned_public_key).verify(sig, data)
    except (ValueError, InvalidSignature, TypeError, binascii.Error) as exc:
        raise BrokerDenied("Broker measurement signature not trusted") from exc
    return claims
