"""Independent, signed evidence gate for AURA physical acceptance.

Only an independently provisioned hardware-laboratory signer can produce
trusted evidence. An Ed25519 signature proves *provenance*, not the presence
of biometric hardware: the operator must audit the signer's physical collection
process and monitor/device identity outside AURA. No private signing key or
Windows Hello access exists in this module.

This gate never grants PermissionEngine rights or activates a skill. Each
acceptance attempt requires exactly one fresh proof for each declared check;
missing, expired, duplicated, unsigned, unverifiable, fabricated or
out-of-budget measurements fail closed without revealing device identifiers.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import math
import re
import time
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, Protocol
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

DOMAIN = b"AURA:PHYSICAL-HARDWARE-EVIDENCE:v1\n"
SCHEMA = "aura.hardware-evidence.v1"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{3,64}$")
_NONCE = re.compile(r"^[0-9a-f]{32}$")


class HardwareCheck(StrEnum):
    WEBAUTHN_UV = "webauthn_uv"
    MICROPHONE_LATENCY = "microphone_latency"
    VOICE_BARGE_IN = "voice_barge_in"
    HUD_MULTIMONITOR = "hud_multimonitor"
    HUD_NEGATIVE_COORDINATES = "hud_negative_coords"
    EMERGENCY_STOP = "emergency_stop"


class EvidenceRejected(PermissionError):
    """The independent physical acceptance proof cannot be trusted."""


@dataclass(frozen=True, slots=True)
class HardwareThresholds:
    """Explicit engineering goals; NEVER assertions of measured performance.

    Limits must be reviewed by the Local Owner for the target device. A p95
    exceeding the configured threshold causes failure, not an adjusted target.
    """
    first_audio_p95_ms: float = 100.0
    barge_in_p95_ms: float = 150.0
    kill_switch_p95_ms: float = 250.0
    minimum_audio_samples: int = 30

    def __post_init__(self) -> None:
        for key in ("first_audio_p95_ms", "barge_in_p95_ms", "kill_switch_p95_ms"):
            value = getattr(self, key)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError("Hardware thresholds must be finite positive numbers")
        if type(self.minimum_audio_samples) is not int or not 10 <= self.minimum_audio_samples <= 10000:
            raise ValueError("Minimum sample count out of bounds")


@dataclass(frozen=True, slots=True)
class SignedHardwareEvidence:
    """Canonical metric envelope signed by a separate hardware test runner.

    Device identities are SHA-256 digests, not serial numbers. The claimed
    environment is signed, but independently attested physical collection
    remains a deployment prerequisite.
    """
    run_id: str
    check: HardwareCheck
    signer_id: str
    device_digest: str
    timestamp: int
    nonce: str
    metrics: Mapping[str, float]
    signature_b64: str
    schema: str = SCHEMA
    environment: str = "physical_windows"

    def __post_init__(self) -> None:
        try:
            if str(UUID(self.run_id)) != self.run_id:
                raise ValueError("Run ID must be a canonical UUID")
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Invalid hardware run identity") from exc
        if not isinstance(self.check, HardwareCheck) or self.schema != SCHEMA:
            raise ValueError("Unsupported hardware evidence schema")
        if not isinstance(self.signer_id, str) or not _IDENTIFIER.fullmatch(self.signer_id):
            raise ValueError("Invalid independent signer identity")
        if not isinstance(self.device_digest, str) or not _DIGEST.fullmatch(self.device_digest):
            raise ValueError("Device identity must be a SHA-256 digest")
        if type(self.timestamp) is not int or self.timestamp <= 0:
            raise ValueError("Invalid signed observation timestamp")
        if not isinstance(self.nonce, str) or not _NONCE.fullmatch(self.nonce):
            raise ValueError("Invalid one-time nonce")
        if self.environment != "physical_windows":
            raise ValueError("Simulated or virtual hardware evidence is not physical acceptance")
        if not isinstance(self.metrics, Mapping) or not 1 <= len(self.metrics) <= 12:
            raise ValueError("Invalid bounded metrics")
        normalized: dict[str, float] = {}
        for key, value in self.metrics.items():
            if not isinstance(key, str) or not _IDENTIFIER.fullmatch(key):
                raise ValueError("Invalid metric key")
            if (not isinstance(value, (int, float)) or isinstance(value, bool)
                    or not math.isfinite(value) or value < 0):
                raise ValueError("Metrics must be finite nonnegative numbers")
            normalized[key] = float(value)
        object.__setattr__(self, "metrics", MappingProxyType(normalized))
        if not isinstance(self.signature_b64, str) or not 1 <= len(self.signature_b64) <= 100:
            raise ValueError("Missing or oversized hardware signature")

    def signing_payload(self) -> bytes:
        """Exactly one stable, non-executable encoding with a domain separator."""
        claims = {
            "schema": self.schema, "environment": self.environment,
            "run_id": self.run_id, "check": self.check.value,
            "signer_id": self.signer_id, "device_digest": self.device_digest,
            "timestamp": self.timestamp, "nonce": self.nonce,
            "metrics": dict(self.metrics),
        }
        return DOMAIN + json.dumps(
            claims, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")


class HardwareEvidenceVerifier(Protocol):
    """Inject a trusted verifier; no unsigned mock may approve production."""

    async def verify(self, evidence: SignedHardwareEvidence) -> bool: ...


class PinnedEd25519HardwareVerifier:
    """Public-key-only verifier for independently generated physical results."""

    def __init__(self, *, trusted_public_keys: Mapping[str, bytes]) -> None:
        if not trusted_public_keys or len(trusted_public_keys) > 8:
            raise ValueError("A bounded set of independent signers is required")
        keys: dict[str, Ed25519PublicKey] = {}
        for name, raw in trusted_public_keys.items():
            if (not isinstance(name, str) or not _IDENTIFIER.fullmatch(name)
                    or not isinstance(raw, bytes) or len(raw) != 32):
                raise ValueError("Malformed independent signer public key")
            keys[name] = Ed25519PublicKey.from_public_bytes(raw)
        self._keys = MappingProxyType(keys)

    async def verify(self, evidence: SignedHardwareEvidence) -> bool:
        if not isinstance(evidence, SignedHardwareEvidence):
            return False
        key = self._keys.get(evidence.signer_id)
        if key is None:
            return False
        try:
            signature = base64.b64decode(evidence.signature_b64, validate=True)
            if len(signature) != 64:
                return False
            # Ed25519 verification is short and public-key-only. CPU-bound work
            # stays off the async event loop.
            await asyncio.to_thread(key.verify, signature, evidence.signing_payload())
            return True
        except (InvalidSignature, ValueError, TypeError, binascii.Error):
            return False


@dataclass(frozen=True, slots=True)
class HardwareAcceptanceReport:
    """Safe summary; not an Owner activation or Kernel authorization token."""
    run_id: str
    accepted: bool
    checked: int
    reason: str
    independently_signed: bool


class HardwareAcceptanceGate:
    """Verify complete signatures, freshness, uniqueness and metric policies."""

    REQUIRED = frozenset(HardwareCheck)

    def __init__(
        self, *, verifier: HardwareEvidenceVerifier,
        thresholds: HardwareThresholds | None = None,
        max_age_seconds: int = 3600,
        verifier_timeout_seconds: float = 5.0,
    ) -> None:
        if not 1 <= max_age_seconds <= 86400 or not 0 < verifier_timeout_seconds <= 30:
            raise ValueError("Invalid hardware acceptance time limits")
        self._verifier = verifier
        self._limits = thresholds or HardwareThresholds()
        self._age = max_age_seconds
        self._timeout = verifier_timeout_seconds

    def _metrics_valid(self, sample: SignedHardwareEvidence) -> bool:
        m, t = sample.metrics, self._limits
        if sample.check is HardwareCheck.WEBAUTHN_UV:
            # UV MAY be a Windows Hello PIN; this does not assert biometrics.
            return all(m.get(key) == 1 for key in (
                "uv_flag_verified", "exact_origin_verified",
                "challenge_replay_rejected", "platform_authenticator",
            ))
        if sample.check in {HardwareCheck.MICROPHONE_LATENCY, HardwareCheck.VOICE_BARGE_IN}:
            p50, p95, n = m.get("p50_ms"), m.get("p95_ms"), m.get("sample_count")
            max_p95 = (t.first_audio_p95_ms if sample.check is HardwareCheck.MICROPHONE_LATENCY
                       else t.barge_in_p95_ms)
            return (p50 is not None and p95 is not None and n is not None
                    and n >= t.minimum_audio_samples and n.is_integer()
                    and 0 <= p50 <= p95 <= max_p95)
        if sample.check is HardwareCheck.HUD_MULTIMONITOR:
            return (m.get("monitor_count", 0) >= 2
                    and m.get("mixed_dpi_verified") == 1
                    and m.get("display_hotplug_verified") == 1)
        if sample.check is HardwareCheck.HUD_NEGATIVE_COORDINATES:
            return (m.get("negative_virtual_x_observed") == 1
                    and m.get("hit_test_verified") == 1
                    and m.get("click_through_verified") == 1)
        if sample.check is HardwareCheck.EMERGENCY_STOP:
            return (m.get("no_new_dispatch_after_kill") == 1
                    and m.get("restart_stays_killed") == 1
                    and m.get("p95_ms", float("inf")) <= t.kill_switch_p95_ms)
        return False

    async def assess(
        self, *, run_id: str, evidence: tuple[SignedHardwareEvidence, ...],
    ) -> HardwareAcceptanceReport:
        """Fail closed on missing proofs, timeouts, false metrics or replay.

        This method does not accept simulated hardware in production; actual
        independent physical instrumentation remains a human-owned task.
        """
        if len(evidence) != len(self.REQUIRED):
            return HardwareAcceptanceReport(run_id, False, 0, "incomplete_evidence", False)
        now = int(time.time())
        seen: set[HardwareCheck] = set()
        seen_nonces: set[str] = set()
        checked = 0
        for item in evidence:
            if not isinstance(item, SignedHardwareEvidence):
                return HardwareAcceptanceReport(run_id, False, checked, "invalid_evidence", False)
            if (item.run_id != run_id or item.check in seen or item.nonce in seen_nonces
                    or not 0 <= now - item.timestamp <= self._age):
                return HardwareAcceptanceReport(run_id, False, checked, "stale_or_repeated", False)
            if not self._metrics_valid(item):
                return HardwareAcceptanceReport(run_id, False, checked, "measurement_failed", False)
            try:
                valid = await asyncio.wait_for(
                    self._verifier.verify(item), timeout=self._timeout,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                return HardwareAcceptanceReport(run_id, False, checked, "verifier_failed", False)
            if valid is not True:
                return HardwareAcceptanceReport(run_id, False, checked, "signature_rejected", False)
            seen.add(item.check)
            seen_nonces.add(item.nonce)
            checked += 1
        complete = seen == self.REQUIRED
        return HardwareAcceptanceReport(
            run_id, complete, checked,
            "verified_physical_evidence" if complete else "missing_checks",
            complete,
        )
