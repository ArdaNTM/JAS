"""Authenticated, replay-resistant handoff of WebAuthn owner decisions.

The Ed25519 *issuer* is instantiated ONLY in the separately privileged owner
control plane after a genuine server-verified WebAuthn decision. AURA Core
receives only trusted public keys and a protected durable receipt-consumption
store. A signed receipt is not a tool execution or sandbox attestation.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from aura_core.enterprise.approval_store import ApprovalRecord, ApprovalStatus
from aura_core.kernel.permissions import AuthorizationDecision, AuthorizationRequest, PermissionEngine, RiskLevel
from uuid import uuid4

DOMAIN = b"AURA:OWNER-RECEIPT:v1\n"
SCHEMA = "aura.owner-receipt.v1"
DIGEST = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[a-zA-Z0-9_-]{3,64}$")


def _canonical(claims: "OwnerReceiptClaims") -> bytes:
    return json.dumps(asdict(claims), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


@dataclass(frozen=True, slots=True)
class OwnerReceiptClaims:
    approval_id: str
    approval_version: int
    binding_digest: str
    policy_digest: str
    operation: str
    principal_id: str
    issued_at: int
    expires_at: int
    nonce: str
    schema: str = SCHEMA

    def __post_init__(self):
        if self.schema != SCHEMA or self.principal_id != "local_owner" or self.operation not in {"activate", "rollback", "revoke"}:
            raise ValueError("Invalid owner approval scope")
        if (not isinstance(self.approval_id, str) or not 1 <= len(self.approval_id) <= 128
            or any(ord(c) < 33 or ord(c) > 126 for c in self.approval_id)):
            raise ValueError("Invalid approval ID")
        if type(self.approval_version) is not int or self.approval_version < 2:
            raise ValueError("Owner decision version required")
        if any(not isinstance(v, str) or DIGEST.fullmatch(v) is None
               for v in (self.binding_digest, self.policy_digest)):
            raise ValueError("Invalid approval digest")
        if not isinstance(self.nonce, str) or re.fullmatch(r"[a-f0-9]{32}", self.nonce) is None:
            raise ValueError("Invalid receipt nonce")
        if type(self.issued_at) is not int or type(self.expires_at) is not int:
            raise ValueError("Invalid receipt time")
        if self.issued_at <= 0 or not 0 < self.expires_at - self.issued_at <= 120:
            raise ValueError("Owner receipt must expire within two minutes")


@dataclass(frozen=True, slots=True)
class SignedOwnerReceipt:
    claims: OwnerReceiptClaims
    key_id: str
    signature_b64: str
    schema: str = SCHEMA

    def __post_init__(self):
        if self.schema != SCHEMA or not isinstance(self.key_id, str) or IDENTIFIER.fullmatch(self.key_id) is None:
            raise ValueError("Invalid receipt signing key ID")
        if not isinstance(self.signature_b64, str) or len(self.signature_b64) > 100:
            raise ValueError("Invalid receipt signature format")

    def encode(self) -> str:
        payload = {"schema": self.schema, "key_id": self.key_id,
                   "claims": asdict(self.claims), "signature_b64": self.signature_b64}
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    @classmethod
    def decode(cls, token: str) -> "SignedOwnerReceipt":
        if not isinstance(token, str) or not 1 <= len(token) <= 4096 or re.fullmatch(r"[A-Za-z0-9_-]+", token) is None:
            raise ValueError("Invalid owner receipt encoding")
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        if base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != token:
            raise ValueError("Non-canonical owner receipt")
        def strict_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate signed receipt JSON field")
                result[key] = value
            return result
        payload = json.loads(raw, object_pairs_hook=strict_object)
        if not isinstance(payload, dict) or set(payload) != {"schema", "key_id", "claims", "signature_b64"}:
            raise ValueError("Unknown owner receipt fields")
        claims = payload["claims"]
        if not isinstance(claims, dict) or set(claims) != set(OwnerReceiptClaims.__dataclass_fields__):
            raise ValueError("Unknown owner receipt claims")
        return cls(
            schema=payload["schema"], key_id=payload["key_id"],
            signature_b64=payload["signature_b64"],
            claims=OwnerReceiptClaims(**claims),
        )


class OwnerReceiptIssuer:
    """Only the trusted owner service may own the signing private key."""

    def __init__(self, *, key_id: str, private_key: Ed25519PrivateKey, policy_digest: str):
        if not isinstance(private_key, Ed25519PrivateKey):
            raise ValueError("Ed25519 private key required")
        if not isinstance(key_id, str) or IDENTIFIER.fullmatch(key_id) is None:
            raise ValueError("Invalid issuer ID")
        if not isinstance(policy_digest, str) or DIGEST.fullmatch(policy_digest) is None:
            raise ValueError("Invalid pinned policy SHA-256")
        self._key_id = key_id
        self._key = private_key
        self._policy = policy_digest

    def issue(self, approval: ApprovalRecord, *, now: int | None = None) -> str:
        if (not isinstance(approval, ApprovalRecord)
            or approval.status is not ApprovalStatus.APPROVED
            or approval.approver_id != "human:local-owner"
            or approval.principal_id != "local_owner"
            or approval.capability_id != "GovernedSkillActivation"
            or approval.decided_at is None
            or approval.operation_id not in {"activate", "rollback", "revoke"}
            or approval.resource_scope != "evolution:skill:" + approval.request_fingerprint
            or not hmac.compare_digest(approval.policy_digest, self._policy)):
            raise PermissionError("Only WebAuthn-verified owner approval is signable")
        timestamp = int(time.time()) if now is None else now
        if type(timestamp) is not int:
            raise ValueError("Invalid issue time")
        if timestamp >= datetime.fromisoformat(approval.expires_at).timestamp():
            raise PermissionError("Owner approval has expired")
        claims = OwnerReceiptClaims(
            approval_id=approval.approval_id, approval_version=approval.version,
            binding_digest=approval.request_fingerprint, policy_digest=approval.policy_digest,
            operation=approval.operation_id, principal_id=approval.principal_id,
            issued_at=timestamp,
            expires_at=min(timestamp+90, int(datetime.fromisoformat(approval.expires_at).timestamp())),
            nonce=secrets.token_hex(16),
        )
        signature = self._key.sign(DOMAIN + _canonical(claims))
        return SignedOwnerReceipt(
            claims=claims, key_id=self._key_id,
            signature_b64=base64.b64encode(signature).decode("ascii"),
        ).encode()


class DurableOwnerReceiptConsumer:
    """Core-side public-key-only authorization and atomic one-shot replay protection."""

    def __init__(self, *, trusted_public_keys: dict[str, bytes], policy_digest: str,
                 permissions: PermissionEngine, ledger_path: str | Path):
        if not isinstance(policy_digest, str) or DIGEST.fullmatch(policy_digest) is None:
            raise ValueError("Pinned owner policy is mandatory")
        if not trusted_public_keys or len(trusted_public_keys) > 8:
            raise ValueError("Trusted owner signing keys are mandatory")
        self._keys: dict[str, Ed25519PublicKey] = {}
        for key_id, raw in trusted_public_keys.items():
            if not isinstance(key_id, str) or IDENTIFIER.fullmatch(key_id) is None or not isinstance(raw, bytes) or len(raw) != 32:
                raise ValueError("Untrusted owner receipt public key")
            self._keys[key_id] = Ed25519PublicKey.from_public_bytes(raw)
        if not isinstance(permissions, PermissionEngine):
            raise ValueError("PermissionEngine mandatory")
        path = Path(ledger_path)
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise ValueError("Pre-provisioned absolute receipt ledger required")
        if path.resolve().is_relative_to(Path(__file__).resolve().parents[4]):
            raise PermissionError("Receipt ledger cannot be in AURA checkout")
        if os.name == "posix" and path.stat().st_mode & 0o077:
            raise PermissionError("Receipt ledger must have owner-only permissions")
        self._db = sqlite3.connect(str(path), timeout=5, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=DELETE")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS consumed_owner_receipts (
                approval_id TEXT PRIMARY KEY,
                nonce TEXT NOT NULL UNIQUE,
                signed_receipt_sha256 TEXT NOT NULL UNIQUE,
                consumed_at INTEGER NOT NULL
            )
        """)
        self._policy = policy_digest
        self._permissions = permissions
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __call__(self, principal_id: str, operation: str, binding_digest: str, receipt: str) -> bool:
        if principal_id != "local_owner" or operation not in {"activate", "rollback", "revoke"}:
            return False
        if not isinstance(binding_digest, str) or DIGEST.fullmatch(binding_digest) is None:
            return False
        try:
            token = SignedOwnerReceipt.decode(receipt)
            claims = token.claims
            now = int(time.time())
            if (claims.principal_id != principal_id or claims.operation != operation
                or not hmac.compare_digest(claims.binding_digest, binding_digest)
                or not hmac.compare_digest(claims.policy_digest, self._policy)
                or not claims.issued_at-30 <= now < claims.expires_at):
                return False
            public_key = self._keys.get(token.key_id)
            if public_key is None:
                return False
            signature = base64.b64decode(token.signature_b64, validate=True)
            if len(signature) != 64:
                return False
            public_key.verify(signature, DOMAIN + _canonical(claims))
        except (InvalidSignature, ValueError, TypeError, KeyError, binascii.Error, OverflowError):
            return False
        decision = self._permissions.authorize(AuthorizationRequest(
            request_id=str(uuid4()), principal_id=principal_id,
            capability_id="GovernedSkillActivation", operation_id=operation,
            resource_scope="evolution:skill:"+binding_digest, risk_level=RiskLevel.CRITICAL,
        ))
        if decision.decision not in {AuthorizationDecision.ALLOW, AuthorizationDecision.REQUIRE_APPROVAL}:
            return False
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute(
                    "INSERT INTO consumed_owner_receipts "
                    "(approval_id, nonce, signed_receipt_sha256, consumed_at) VALUES (?,?,?,?)",
                    (claims.approval_id, claims.nonce, hashlib.sha256(receipt.encode("ascii")).hexdigest(),
                     int(time.time())),
                )
                self._db.execute("COMMIT")
                return True
            except sqlite3.IntegrityError:
                self._db.execute("ROLLBACK")
                return False
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
