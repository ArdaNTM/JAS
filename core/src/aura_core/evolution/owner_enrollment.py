"""One-time, operator-bootstrapped WebAuthn enrollment ceremony.

Only a separately launched local owner service may use this module. Initial
enrollment cannot be authorized by AURA's agent or normal UI bearer tokens.
Operator must provision a 256-bit secret *outside* the checkout under OS ACL.
The fido2 server verifies origin, RP, challenge, UP+UV and attested credential
metadata before storing public credential configuration.
"""
from __future__ import annotations

import hmac
import json
import os
from pathlib import Path
import secrets
import threading
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

ORIGIN = "http://localhost:8766"
RP_ID = "localhost"


class ProtectedEnrollment:
    """Single-use local ceremony, bound to one owner-controlled config output."""

    def __init__(self, *, bootstrap_secret: str, config_output: Path,
                 policy_digest: str, ttl_seconds: int = 90):
        # Strong random token from protected operator provisioning, NOT from Core.
        if not isinstance(bootstrap_secret, str) or len(bootstrap_secret) != 64 or any(
            c not in "0123456789abcdef" for c in bootstrap_secret
        ):
            raise ValueError("256-bit hex operator bootstrap token required")
        if not isinstance(policy_digest, str) or len(policy_digest) != 64 or any(
            c not in "0123456789abcdef" for c in policy_digest
        ):
            raise ValueError("Pinned JAS owner-policy digest required")
        path = Path(config_output)
        if (not path.is_absolute() or path.is_symlink() or path.exists()
            or not path.parent.is_dir()
            or path.resolve().is_relative_to(Path(__file__).resolve().parents[4])):
            raise PermissionError("New owner credential output must be outside AURA checkout")
        if type(ttl_seconds) is not int or not 30 <= ttl_seconds <= 120:
            raise ValueError("Enrollment TTL must be between 30 and 120 seconds")

        from fido2.server import Fido2Server
        self._server = Fido2Server(
            {"id": RP_ID, "name": "AURA Local Owner"},
            attestation="none",
            verify_origin=lambda origin: origin == ORIGIN,
        )
        self._secret = bootstrap_secret
        self._policy = policy_digest
        self._path = path
        self._ttl = ttl_seconds
        self._lock = threading.RLock()
        self._state: dict | None = None
        self._deadline = 0.0
        self._completed = False

    def _authorize(self, token: str) -> None:
        if not isinstance(token, str) or not hmac.compare_digest(token, self._secret):
            raise PermissionError("Invalid owner bootstrap secret")
        if self._completed or self._path.exists():
            raise PermissionError("Owner enrollment already completed")

    def begin(self, token: str) -> dict:
        with self._lock:
            self._authorize(token)
            if self._state is not None and time.monotonic() < self._deadline:
                raise PermissionError("Only one pending enrollment challenge allowed")
            from fido2.webauthn import (
                AuthenticatorAttachment, ResidentKeyRequirement, UserVerificationRequirement,
            )
            options, state = self._server.register_begin(
                user={"id": secrets.token_bytes(32),
                      "name": "local_owner", "display_name": "AURA Local Owner"},
                credentials=[],
                resident_key_requirement=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED,
                authenticator_attachment=AuthenticatorAttachment.PLATFORM,
                challenge=secrets.token_bytes(32),
            )
            self._state = state
            self._deadline = time.monotonic() + self._ttl
            # fido2 v2 WebAuthn JSON serialization: binary values -> base64url.
            result = json.loads(options.to_json())
            return result

    def complete(self, token: str, response: dict) -> dict:
        with self._lock:
            self._authorize(token)
            if self._state is None or time.monotonic() >= self._deadline:
                raise PermissionError("Owner enrollment challenge missing or expired")
            # Consume the one-shot challenge even if validation fails; no retries
            # with a captured or replayed attestation response.
            state, self._state = self._state, None
            if not isinstance(response, dict) or len(json.dumps(response)) > 32768:
                raise PermissionError("Invalid or oversized WebAuthn registration")
            try:
                auth = self._server.register_complete(state, response)
                if not auth.is_user_present() or not auth.is_user_verified():
                    raise PermissionError("Owner presence and verification required")
                credential = auth.credential_data
                if credential is None:
                    raise PermissionError("No attested public credential")
                cose = credential.public_key
                if cose.get(1) != 2 or cose.get(3) != -7 or cose.get(-1) != 1:
                    raise PermissionError("Only ES256 P-256 credentials supported")
                x, y = cose.get(-2), cose.get(-3)
                if (not isinstance(x, bytes) or not isinstance(y, bytes)
                    or len(x) != 32 or len(y) != 32):
                    raise PermissionError("Invalid ES256 credential coordinates")
                public_key = ec.EllipticCurvePublicNumbers(
                    int.from_bytes(x, "big"), int.from_bytes(y, "big"),
                    ec.SECP256R1(),
                ).public_key()
                import base64
                credential_id = base64.urlsafe_b64encode(
                    credential.credential_id
                ).rstrip(b"=").decode("ascii")
                config = {
                    "rp_id": RP_ID, "origin": ORIGIN,
                    "credential_id": credential_id,
                    "public_key_pem": public_key.public_bytes(
                        serialization.Encoding.PEM,
                        serialization.PublicFormat.SubjectPublicKeyInfo,
                    ).decode("ascii"),
                    "policy_digest": self._policy,
                }
                # Exclusive creation: existing owner credential cannot be
                # silently replaced. Operator must manage rotation separately.
                with self._path.open("x", encoding="utf-8") as stream:
                    os.chmod(self._path, 0o600)
                    json.dump(config, stream, sort_keys=True, separators=(",", ":"))
                    stream.flush()
                    os.fsync(stream.fileno())
                self._completed = True
            except (ValueError, TypeError, KeyError) as exc:
                raise PermissionError("WebAuthn registration rejected") from exc
            return {
                "status": "enrolled", "credential_id": credential_id,
                "owner_configuration_written": True,
                "tool_activated": False,
            }
