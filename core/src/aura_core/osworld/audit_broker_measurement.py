"""F2.3-C: signed, nonce-bound broker measurement transaction.

The F2.1 Windows service intentionally remains deny-only and DOES NOT wire
this handler to its named pipe. A future reviewed service-mode change must
prove separated Windows/daemon identities and broker-owned key provisioning
before enabling it. This module never signs the AuraAuditor host receipt.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
import json
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .audit_broker_protocol import (
    AuditRequest, BrokerDenied, authorize_request, parse_request,
)
from .audit_broker_receipt import SCHEMA, sign_measurement
from .audit_broker_topology import BrokerTopologyAudit
from .audit_broker_windows import MAX_RESPONSE_BYTES


def _validate_peer(peer_sid: str, auditor_sid: str) -> None:
    """Reject untrusted client *before* any privileged Docker inspection."""
    from .audit_broker_service import SID_PATTERN
    if (type(peer_sid) is not str or type(auditor_sid) is not str
            or SID_PATTERN.fullmatch(peer_sid) is None
            or SID_PATTERN.fullmatch(auditor_sid) is None
            or peer_sid != auditor_sid):
        raise BrokerDenied("Only the independent AuraAuditor may request a measurement")


def evaluate_broker_measurement(
    raw: bytes,
    *,
    peer_sid: str,
    auditor_sid: str,
    topology: BrokerTopologyAudit,
    claim_nonce: Callable[[str], bool],
    signer: Ed25519PrivateKey,
    now: int | None = None,
) -> bytes:
    """One authenticated, bounded, signed measurement; failures never sign.

    A live service MUST pass peer_sid measured from the Windows named-pipe
    OS impersonation token, a broker-owned DurableNonceStore.claim callback,
    an immutable protected VM image, and a separately protected broker key.
    These are trusted constructor inputs, never values from request JSON.
    """
    _validate_peer(peer_sid, auditor_sid)
    if not isinstance(topology, BrokerTopologyAudit):
        raise BrokerDenied("Broker requires the complete governed topology policy")
    if not isinstance(signer, Ed25519PrivateKey):
        raise BrokerDenied("Broker service signing key is unavailable")
    clock = int(time.time()) if now is None else now
    if type(clock) is not int:
        raise BrokerDenied("Invalid trusted broker clock")
    request = parse_request(raw, now=clock)

    # Run/container identity comes from an independent, allowlisted Docker
    # inspection BEFORE atomically consuming the nonce; the request cannot
    # provide its own measured identity or Docker commands.
    measured_run_id, measured_container_id = topology.measured_identity(
        request.container_id,
    )
    authorize_request(
        request, now=clock, peer_sid=peer_sid, auditor_sid=auditor_sid,
        measured_run_id=measured_run_id,
        measured_container_id=measured_container_id,
        claim_nonce=claim_nonce,
    )
    boot, ports, checks = topology.audit(request)
    if not isinstance(ports, dict) or not isinstance(checks, dict):
        raise BrokerDenied("Incomplete measured network evidence")
    claims: dict[str, object] = {
        "schema": SCHEMA,
        "run_id": request.run_id,
        "container_id": request.container_id,
        "nonce": request.nonce,
        "checked_at": int(time.time()) if now is None else clock,
        "boot": asdict(boot),
        "host_ports": ports,
        "checks": checks,
    }
    envelope = sign_measurement(claims, signer=signer)
    wire = json.dumps(
        envelope, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("ascii")
    if len(wire) > MAX_RESPONSE_BYTES:
        raise BrokerDenied("Broker measurement exceeds bounded IPC response")
    return wire
