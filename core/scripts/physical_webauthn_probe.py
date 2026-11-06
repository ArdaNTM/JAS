"""Interactive *real* Windows Hello / FIDO2 platform authenticator probe.

Uses python-fido2 2.2.1's WindowsClient -> native Windows WebAuthn API, not a
software mock. Registers a temporary credential for this run under a strict
localhost RP, verifies both creation and assertion on a separate local
Fido2Server instance, rejects reusing the first assertion with a second
challenge, and requires the authenticator UV flag.

It never issues an AURA Owner receipt and never stores private keys. This is an
independent physical *diagnostic*, not proof that AURA's separate Owner Control
Plane has approved a specific pending MCP operation. Windows Hello PIN can
satisfy UV; this cannot claim that a biometric sensor was used.

Run interactively in an unprivileged Windows session:
    uv run --frozen python scripts/physical_webauthn_probe.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import sys
from dataclasses import dataclass
from typing import Any


class HardwareUnavailable(RuntimeError):
    """Native Windows Hello/WebAuthn prompt could not complete."""


@dataclass(frozen=True, slots=True)
class WebAuthnProbeResult:
    """No synthetic fallback or passkey authority; only measured observations."""
    native_windows_webauthn: bool
    registration_verified: bool
    assertion_verified: bool
    uv_flag_verified: bool
    exact_origin_verified: bool
    challenge_replay_rejected: bool
    platform_authenticator_requested: bool
    independent_owner_receipt_issued: bool = False

    def public(self) -> dict[str, object]:
        return {
            "check": "webauthn_uv",
            "native_windows_webauthn": self.native_windows_webauthn,
            "registration_verified": self.registration_verified,
            "assertion_verified": self.assertion_verified,
            "uv_flag_verified": self.uv_flag_verified,
            "exact_origin_verified": self.exact_origin_verified,
            "challenge_replay_rejected": self.challenge_replay_rejected,
            "platform_authenticator_requested": self.platform_authenticator_requested,
            "owner_approval_granted": False,
            "hardware_verified": False,
            "reason": "Diagnostic only: independent signed evidence and remaining hardware checks required",
        }


def verify_selected_assertion(
    server: Any, state: Any, credentials: list[Any], selection: Any,
) -> Any:
    """Verify the python-fido2 2.x AssertionSelection correctly.

    WindowsClient.get_assertion() returns AssertionSelection, not an
    AuthenticationResponse. Its get_response(0) returns the full WebAuthn
    AuthenticationResponse expected by Fido2Server.authenticate_complete.
    AttestedCredentialData (the server's return value) is *not* the
    authenticator data and cannot be queried for the UV bit.
    """
    get_response = getattr(selection, "get_response", None)
    if not callable(get_response):
        raise HardwareUnavailable("Windows FIDO2 client returned no assertion selection")
    try:
        assertion = get_response(0)
    except (IndexError, ValueError, TypeError) as exc:
        raise HardwareUnavailable("No usable authenticator assertion") from exc
    inner = getattr(assertion, "response", None)
    auth_data = getattr(inner, "authenticator_data", None)
    if auth_data is None or not callable(getattr(auth_data, "is_user_verified", None)):
        raise HardwareUnavailable("Invalid WebAuthn assertion payload")
    # This raises on the wrong challenge, origin, RP ID or invalid signature.
    # Never interpret an unverified assertion's UV bit as proof.
    server.authenticate_complete(state, credentials, assertion)
    if auth_data.is_user_verified() is not True:
        raise HardwareUnavailable("Verified assertion lacks the required UV flag")
    return assertion


def _run_platform_authenticator() -> WebAuthnProbeResult:
    """Real native Win32 prompt; must be called from the physical console."""
    if sys.platform != "win32":
        raise HardwareUnavailable("Windows 10 1903+ / Windows 11 required")
    import ctypes

    if ctypes.windll.shell32.IsUserAnAdmin():
        raise HardwareUnavailable("Run with an ordinary logged-in user; do not elevate")
    from fido2.client import DefaultClientDataCollector
    from fido2.client.windows import WindowsClient
    from fido2.server import Fido2Server

    if not WindowsClient.is_available():
        raise HardwareUnavailable("Windows WebAuthn native API unavailable")
    origin = "https://localhost"
    rp_id = "localhost"
    server = Fido2Server(
        {"id": rp_id, "name": "AURA Physical Acceptance (temporary)"},
        verify_origin=lambda actual: actual == origin,
    )
    client = WindowsClient(DefaultClientDataCollector(origin))
    user = {
        "id": secrets.token_bytes(32),
        "name": "aura-physical-test",
        "displayName": "AURA Physical Test",
    }
    creation, registration_state = server.register_begin(
        user, user_verification="required",
        authenticator_attachment="platform",
    )
    print("Windows Hello: confirm TEMPORARY passkey registration on this machine.", file=sys.stderr)
    registration = client.make_credential(creation["publicKey"])
    registration_data = server.register_complete(registration_state, registration)
    if (registration_data.credential_data is None
            or not registration_data.is_user_verified()):
        raise HardwareUnavailable("Windows Hello did not attest required user verification")
    credentials = [registration_data.credential_data]
    request, assertion_state = server.authenticate_begin(
        credentials=credentials, user_verification="required",
    )
    print("Windows Hello: confirm the second, fresh assertion.", file=sys.stderr)
    selection = client.get_assertion(request["publicKey"])
    assertion = verify_selected_assertion(server, assertion_state, credentials, selection)
    # Original VALID assertion MUST fail against a distinct challenge.
    _, fresh_state = server.authenticate_begin(
        credentials=credentials, user_verification="required",
    )
    try:
        server.authenticate_complete(fresh_state, credentials, assertion)
    except ValueError:
        rejected_replay = True
    else:
        rejected_replay = False
    if not rejected_replay:
        raise HardwareUnavailable("Verifier did not reject an assertion against a fresh challenge")
    return WebAuthnProbeResult(
        native_windows_webauthn=True,
        registration_verified=True,
        assertion_verified=True,
        uv_flag_verified=True,
        exact_origin_verified=True,
        challenge_replay_rejected=True,
        platform_authenticator_requested=True,
    )


async def run() -> WebAuthnProbeResult:
    """Windows API blocks for user presence; run it off the asyncio loop."""
    return await asyncio.to_thread(_run_platform_authenticator)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args(argv)
    try:
        result = asyncio.run(run())
        print(json.dumps(result.public(), indent=2))
        return 0
    except Exception as exc:
        # Fail closed even for native FIDO2 ClientError or unexpected SDK types.
        # Never print raw WebAuthn responses, credential IDs or private material.
        print(json.dumps({
            "check": "webauthn_uv",
            "hardware_verified": False,
            "error_type": type(exc).__name__,
            "stage": "native_webauthn_validation",
            "independent_owner_receipt_issued": False,
        }, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
