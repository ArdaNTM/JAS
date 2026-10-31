"""Owner passkey / Windows Hello WebAuthn assertion verifier (backend only).

This module verifies FIDO2/WebAuthn *authentication*, not mere browser clicks.
Enrollment, server-issued one-shot challenge persistence, origin transport and
the protected approval decision service MUST be handled by a separate owner
control plane. Until provisioned, the Evolution UI stays review-only.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64url(raw: str, *, max_chars: int) -> bytes:
    if not isinstance(raw, str) or not 1 <= len(raw) <= max_chars or not re.fullmatch(r"[A-Za-z0-9_-]+", raw):
        raise ValueError("Invalid WebAuthn base64url input")
    data = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    if base64.urlsafe_b64encode(data).decode().rstrip("=") != raw:
        raise ValueError("Non-canonical WebAuthn base64url")
    return data


def _unique_dict(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for k, v in pairs:
        if k in result:
            raise ValueError("Duplicate WebAuthn JSON key")
        result[k] = v
    return result


@dataclass(frozen=True, slots=True)
class WebAuthnOwnerAssertion:
    credential_id: str
    client_data_json: str
    authenticator_data: str
    signature: str


class OwnerPasskeyVerifier:
    """Verify existing enrolled P-256 credentials, origin/RP, UP+UV and counter.

    Must be called ONLY with a trusted control-plane issued fresh challenge
    (not a challenge taken from the client's request). Caller must atomically
    consume the challenge and persist sign_count in a protected owner store.
    """

    def __init__(self, *, rp_id: str, origin: str, credential_id: str, public_key_pem: bytes) -> None:
        if not isinstance(rp_id, str) or rp_id != "localhost":
            raise ValueError("Local WebAuthn requires explicit localhost RP ID")
        if not isinstance(origin, str) or origin not in {"http://localhost:5173", "https://localhost:5173", "http://localhost:8766"}:
            raise ValueError("Explicit pinned localhost origin required")
        credential = _b64url(credential_id, max_chars=512)
        if not 16 <= len(credential) <= 256:
            raise ValueError("Invalid registered credential ID")
        if not isinstance(public_key_pem, bytes) or len(public_key_pem) > 4096:
            raise ValueError("Invalid public key")
        key = serialization.load_pem_public_key(public_key_pem)
        if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
            raise ValueError("Only WebAuthn ES256 P-256 credential keys are supported")
        self._key = key
        self._credential = credential
        self._origin = origin
        self._rp_hash = hashlib.sha256(rp_id.encode()).digest()

    def verify(
        self, assertion: WebAuthnOwnerAssertion, *,
        expected_challenge: bytes, previous_counter: int,
    ) -> int:
        if not isinstance(assertion, WebAuthnOwnerAssertion):
            raise PermissionError("Authenticated passkey assertion required")
        if not isinstance(expected_challenge, bytes) or not 32 <= len(expected_challenge) <= 128:
            raise ValueError("Trusted challenge must contain 32-128 random bytes")
        if type(previous_counter) is not int or not 0 <= previous_counter < 2**32:
            raise ValueError("Stored signature counter is invalid")
        try:
            if _b64url(assertion.credential_id, max_chars=512) != self._credential:
                raise PermissionError("Unknown owner credential")
            client_raw = _b64url(assertion.client_data_json, max_chars=8192)
            auth = _b64url(assertion.authenticator_data, max_chars=4096)
            sig = _b64url(assertion.signature, max_chars=1024)
            if len(auth) < 37:
                raise PermissionError("Authenticator data too short")
            client = json.loads(client_raw, object_pairs_hook=_unique_dict)
            if not isinstance(client, dict) or client.get("type") != "webauthn.get":
                raise PermissionError("Not a WebAuthn authentication assertion")
            if client.get("origin") != self._origin or client.get("crossOrigin", False) is not False:
                raise PermissionError("WebAuthn origin mismatch")
            if client.get("topOrigin") not in (None, self._origin):
                raise PermissionError("Unexpected WebAuthn top origin")
            if _b64url(client.get("challenge"), max_chars=256) != expected_challenge:
                raise PermissionError("WebAuthn challenge mismatch")
            if auth[:32] != self._rp_hash:
                raise PermissionError("RP ID hash mismatch")
            flags = auth[32]
            if flags & 0x05 != 0x05:  # UP + UV
                raise PermissionError("Owner user presence and verification required")
            counter = int.from_bytes(auth[33:37], "big")
            # Some platform authenticators keep a zero counter; otherwise
            # reject cloned/stale responses. Control plane stores counter.
            if (previous_counter > 0 and counter == 0) or (
                previous_counter > 0 and counter <= previous_counter
            ):
                raise PermissionError("WebAuthn sign counter rollback detected")
            self._key.verify(sig, auth + hashlib.sha256(client_raw).digest(),
                             ec.ECDSA(hashes.SHA256()))
        except (InvalidSignature, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise PermissionError("Invalid owner passkey assertion") from exc
        return counter
