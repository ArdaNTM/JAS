"""Ed25519-verified sandbox evidence (Core has public keys ONLY).

Signing must happen in a separate, trusted runner process that independently
observes an isolated job. The untrusted sandbox output cannot mint evidence.
This verifier has no private-key interface and performs no model/tool execution.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import threading
import time
from dataclasses import asdict, dataclass
from typing import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SCHEMA = "aura.sandbox-attestation.v1"
DOMAIN = b"AURA:SANDBOX-ATTESTATION:v1\n"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_RUN = re.compile(r"^[a-zA-Z0-9_-]{16,128}$")
_KEY = re.compile(r"^[a-zA-Z0-9_-]{3,64}$")


def _digest(value: str) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def canonical_claims(claims: "SandboxClaims") -> bytes:
    """One canonical encoding for signing and verification; no floats."""
    return json.dumps(
        asdict(claims), sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


@dataclass(frozen=True, slots=True)
class SandboxClaims:
    source_sha256: str
    tests_sha256: str
    image_digest: str  # OCI content digest, NEVER a mutable tag
    policy_sha256: str
    binding_digest: str  # Entire reviewed MCP SkillBinding
    run_id: str
    runner_id: str
    issued_at: int
    expires_at: int
    exit_code: int
    outcome: str
    network_disabled: bool
    rootfs_readonly: bool
    schema: str = SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SCHEMA:
            raise ValueError("Unknown attestation schema")
        for field in ("source_sha256", "tests_sha256", "policy_sha256", "binding_digest"):
            if not _digest(getattr(self, field)):
                raise ValueError("Invalid SHA-256 identity: " + field)
        if not isinstance(self.image_digest, str) or not self.image_digest.startswith("sha256:") or not _digest(self.image_digest[7:]):
            raise ValueError("Image must be pinned by OCI SHA-256")
        if not isinstance(self.run_id, str) or not _RUN.fullmatch(self.run_id):
            raise ValueError("Invalid unique runner job identifier")
        if not isinstance(self.runner_id, str) or not _KEY.fullmatch(self.runner_id):
            raise ValueError("Invalid runner identity")
        if type(self.issued_at) is not int or type(self.expires_at) is not int:
            raise ValueError("Time must be Unix seconds")
        if self.issued_at <= 0 or self.expires_at <= self.issued_at or self.expires_at - self.issued_at > 900:
            raise ValueError("Invalid evidence lifetime")
        if type(self.exit_code) is not int or self.exit_code != 0 or self.outcome != "passed":
            raise ValueError("Only successful independently observed runs are attestable")
        if self.network_disabled is not True or self.rootfs_readonly is not True:
            raise ValueError("Required isolation conditions not observed")


@dataclass(frozen=True, slots=True)
class SignedSandboxAttestation:
    key_id: str
    claims: SandboxClaims
    signature_b64: str
    schema: str = SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SCHEMA or not isinstance(self.key_id, str) or not _KEY.fullmatch(self.key_id):
            raise ValueError("Invalid signed evidence envelope")
        if not isinstance(self.signature_b64, str) or len(self.signature_b64) > 100:
            raise ValueError("Invalid signature encoding")

    def to_dict(self) -> dict:
        return {"schema": self.schema, "key_id": self.key_id,
                "claims": asdict(self.claims), "signature_b64": self.signature_b64}

    @classmethod
    def from_dict(cls, value: dict) -> "SignedSandboxAttestation":
        if not isinstance(value, dict) or set(value) != {"schema", "key_id", "claims", "signature_b64"}:
            raise ValueError("Unexpected attestation envelope fields")
        claims = value["claims"]
        if not isinstance(claims, dict) or set(claims) != set(SandboxClaims.__dataclass_fields__):
            raise ValueError("Unexpected evidence claim fields")
        return cls(schema=value["schema"], key_id=value["key_id"],
                   claims=SandboxClaims(**claims), signature_b64=value["signature_b64"])


class IndependentAttestationVerifier:
    """Pinned trust policy; public keys alone do not certify sandbox isolation."""

    def __init__(
        self, *, trusted_public_keys: Mapping[str, bytes],
        expected_image_digest: str, expected_policy_sha256: str,
        expected_tests_sha256: str, trusted_runner_id: str,
        clock_skew_seconds: int = 30,
    ) -> None:
        if not trusted_public_keys or len(trusted_public_keys) > 8:
            raise ValueError("Trusted attestor public keys are mandatory")
        self._keys: dict[str, Ed25519PublicKey] = {}
        for name, raw in trusted_public_keys.items():
            if not isinstance(name, str) or not _KEY.fullmatch(name) or not isinstance(raw, bytes) or len(raw) != 32:
                raise ValueError("Invalid trusted attestor public key")
            self._keys[name] = Ed25519PublicKey.from_public_bytes(raw)
        if not isinstance(expected_image_digest, str) or not expected_image_digest.startswith("sha256:") or not _digest(expected_image_digest[7:]):
            raise ValueError("OCI image must be digest-pinned")
        if not _digest(expected_policy_sha256) or not _digest(expected_tests_sha256):
            raise ValueError("Attestation policy/test digests required")
        if not isinstance(trusted_runner_id, str) or not _KEY.fullmatch(trusted_runner_id):
            raise ValueError("Trusted runner identity required")
        if type(clock_skew_seconds) is not int or not 0 <= clock_skew_seconds <= 60:
            raise ValueError("Unsafe verifier clock skew")
        self._image = expected_image_digest
        self._policy = expected_policy_sha256
        self._tests = expected_tests_sha256
        self._runner = trusted_runner_id
        self._skew = clock_skew_seconds

    def verify(self, envelope: SignedSandboxAttestation, *, source_sha256: str,
               binding_digest: str, now: int | None = None) -> bool:
        if not _digest(source_sha256) or not _digest(binding_digest):
            return False
        if not isinstance(envelope, SignedSandboxAttestation):
            return False
        c = envelope.claims
        current = int(time.time()) if now is None else now
        if type(current) is not int or not c.issued_at - self._skew <= current < c.expires_at:
            return False
        if (c.source_sha256 != source_sha256 or c.binding_digest != binding_digest
                or c.image_digest != self._image or c.policy_sha256 != self._policy
                or c.tests_sha256 != self._tests or c.runner_id != self._runner):
            return False
        public_key = self._keys.get(envelope.key_id)
        if public_key is None:
            return False
        try:
            signature = base64.b64decode(envelope.signature_b64, validate=True)
            if len(signature) != 64:
                return False
            public_key.verify(signature, DOMAIN + canonical_claims(c))
        except (InvalidSignature, binascii.Error, ValueError, TypeError):
            return False
        return True


class AttestationReceiptRegistry:
    """Fail-closed bounded receipts; rejects duplicate run registration.

    Trust roots MUST be external immutable configuration. This in-memory
    registry is a prototype; production replay ledger must be durable and
    owned by an independent, non-agent-writable control plane.
    """

    def __init__(self, verifier: IndependentAttestationVerifier,
                 max_receipts: int = 128) -> None:
        if not isinstance(verifier, IndependentAttestationVerifier):
            raise ValueError("Independent verifier required")
        if not 1 <= max_receipts <= 4096:
            raise ValueError("Invalid evidence capacity")
        self._verifier = verifier
        self._max_receipts = max_receipts
        self._receipts: dict[str, SignedSandboxAttestation] = {}
        self._run_ids: set[tuple[str, str]] = set()
        self._lock = threading.RLock()

    def register(self, envelope: SignedSandboxAttestation, *,
                 source_sha256: str, binding_digest: str, now: int | None = None) -> str:
        with self._lock:
            if not self._verifier.verify(envelope, source_sha256=source_sha256,
                                         binding_digest=binding_digest, now=now):
                raise PermissionError("Untrusted sandbox attestation")
            run_key = (envelope.key_id, envelope.claims.run_id)
            if run_key in self._run_ids:
                raise PermissionError("Attestation run already registered")
            if len(self._receipts) >= self._max_receipts:
                raise PermissionError("Attestation registry full")
            blob = json.dumps(envelope.to_dict(), sort_keys=True,
                              separators=(",", ":")).encode()
            receipt = hashlib.sha256(DOMAIN + blob).hexdigest()
            self._receipts[receipt] = envelope
            self._run_ids.add(run_key)
            return receipt

    def verify_binding(self, binding: object, receipt: str) -> bool:
        with self._lock:
            if not isinstance(receipt, str):
                return False
            envelope = self._receipts.get(receipt)
            if envelope is None:
                return False
            return self._verifier.verify(
                envelope, source_sha256=getattr(binding, "source_sha256", None),
                binding_digest=getattr(binding, "review_digest", None),
            )
