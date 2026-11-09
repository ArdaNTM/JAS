"""F2.7 fail-closed, UNSIGNED remote OSWorld network audit bridge.

Only called by the Windows SCM adapter AFTER a separately signed operator
approval has been verified and consumed by a durable local nonce ledger.
An observation is NOT an ISOLATION_SIGNED attestation or capability grant.
All Docker operations are delegated to the remote SO_PEERCRED-constrained
root helper through the fixed SSH forced command. No agent-provided command.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Callable

from .audit_broker_protocol import BrokerDenied, parse_request
from .audit_broker_service import STATE_ROOT, validate_service_identity
from .audit_broker_f27_activation import ApprovedActivation
from .audit_broker_ubuntu_transport import (
    UbuntuBrokerSshTransport, UbuntuDockerAuditBackend,
)
from .audit_broker_windows import current_process_sid
from . import network_audit

LEDGER = STATE_ROOT / "f27-nonces.sqlite3"
RESPONSE_SCHEMA = "aura.osworld.f27-unsigned-observation.v1"
_DENIED = b'{"status":"ISOLATION_BLOCKED","signed":false}'


class DurableWindowsNonceStore:
    """SQLite PRIMARY KEY + BEGIN IMMEDIATE; no expiry-based nonce reuse.

    Production state must be pre-provisioned by an independent administrator.
    This process never creates a new production security directory or ledger.
    The state directory and DB must be inaccessible to Agent/Auditor, and the
    Broker must have exactly the database write permissions it needs.
    """

    def __init__(self, path: Path = LEDGER, *, enforce_host: bool = True) -> None:
        if not isinstance(path, Path):
            raise BrokerDenied("Invalid local replay-store path")
        if enforce_host:
            if os.name != "nt" or path != LEDGER:
                raise BrokerDenied("Windows broker nonce store is not pinned")
            from aura_core.evolution.windows_owner_storage import require_private_acl
            if not path.is_file() or path.is_symlink():
                raise BrokerDenied("Operator-provisioned replay DB is missing")
            require_private_acl(path.parent)
            require_private_acl(path)
        self.path = path
        self.enforce_host = enforce_host
        if not enforce_host:
            with self._connection() as db:
                db.execute("CREATE TABLE IF NOT EXISTS consumed ("
                           "nonce TEXT PRIMARY KEY, kind TEXT NOT NULL,"
                           "seen_at INTEGER NOT NULL)")
                db.commit()
        else:
            with self._connection() as db:
                found = db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='consumed'"
                ).fetchone()
                if found != ("consumed",):
                    raise BrokerDenied("Replay ledger has not been independently initialized")

    def _connection(self) -> sqlite3.Connection:
        if self.enforce_host:
            from aura_core.evolution.windows_owner_storage import require_private_acl
            require_private_acl(self.path)
        return sqlite3.connect(self.path, timeout=5, isolation_level=None)

    def claim(self, nonce: str, *, kind: str) -> bool:
        from .audit_broker_protocol import _HEX32
        if (type(nonce) is not str or _HEX32.fullmatch(nonce) is None
                or kind not in ("operator", "request")):
            raise BrokerDenied("Invalid Windows replay nonce")
        try:
            with self._connection() as db:
                db.execute("BEGIN IMMEDIATE")
                accepted = db.execute(
                    "INSERT OR IGNORE INTO consumed (nonce,kind,seen_at) VALUES (?,?,?)",
                    (nonce, kind, int(time.time())),
                ).rowcount == 1
                db.commit()
                return accepted
        except sqlite3.Error as exc:
            raise BrokerDenied("Windows durable replay ledger unavailable") from exc


def inspect_approved_run(
    raw: bytes, peer_sid: str, approved: ApprovedActivation,
    *, claim_nonce: Callable[[str], bool],
    backend_factory: Callable[..., object] = UbuntuDockerAuditBackend,
    transport_factory: Callable[[], object] = UbuntuBrokerSshTransport,
    now: int | None = None,
) -> bytes:
    """One exact approved run, exact VM, authenticated auditor and nonce.

    The caller supplies only the signed, operator-approved capability.
    The parser excludes Docker CLI, address, command and mutable host inputs.
    Any measurement exception is propagated and the pipe responds DENIED.
    """
    if type(approved) is not ApprovedActivation:
        raise BrokerDenied("Missing independently approved activation")
    epoch = int(time.time()) if now is None else now
    if type(epoch) is not int or epoch >= approved.expires_at:
        raise BrokerDenied("Operator approval expired")
    request = parse_request(raw, now=epoch)
    if (peer_sid != approved.policy.auditor_sid
            or request.run_id != approved.run_id
            or request.container_id != approved.vm_id):
        raise BrokerDenied("Auditor or run/VM identity mismatch")
    if not callable(claim_nonce) or claim_nonce(request.nonce) is not True:
        raise BrokerDenied("Windows audit request replay")
    transport = transport_factory()
    backend = backend_factory(
        transport=transport, run_id=approved.run_id, vm_id=approved.vm_id,
    )
    call_docker = backend.policy_inspect
    boot, ports, gateway = network_audit.inspect_topology(
        request.container_id,
        expected_vm_hash=approved.vm_disk_sha256,
        docker_json_fn=call_docker,
    )
    ingress = call_docker([
        "network", "inspect", network_audit.INGRESS_PREFIX + request.run_id,
    ])
    if (type(ingress) is not list or len(ingress) != 1
            or type(ingress[0]) is not dict):
        raise BrokerDenied("Untrusted ingress network inspection")
    try:
        ingress_gateway = ingress[0]["IPAM"]["Config"][0]["Gateway"]
    except (KeyError, TypeError, IndexError) as exc:
        raise BrokerDenied("Missing ingress gateway") from exc
    if type(ingress_gateway) is not str:
        raise BrokerDenied("Malformed ingress gateway")
    probes = backend.fixed_probe
    vm_checks = network_audit.negative_network_probes(
        request.container_id, gateway,
        probe_check=lambda cid, name, host: probes(
            container_id=cid, name=name, gateway_ip=host,
        ),
    )
    gateway_checks = network_audit.negative_network_probes(
        boot.gateway_container_id, ingress_gateway,
        probe_check=lambda cid, name, host: probes(
            container_id=cid, name=name, gateway_ip=host,
        ),
    )
    checks = {
        "network_internal": True,
        "single_network": True,
        "loopback_ports": True,
        "unprivileged": True,
        "no_docker_socket": True,
        "image_pinned": True,
        "gateway_topology": True,
        **vm_checks,
        **{"gateway_" + k: value for k, value in gateway_checks.items()},
    }
    if set(checks) != network_audit.REQUIRED_CHECKS or not all(v is True for v in checks.values()):
        raise BrokerDenied("Incomplete or failed negative network isolation checks")
    if type(ports) is not dict:
        raise BrokerDenied("Malformed port observation")
    # Explicit UNSIGNED status: the broker does not issue an isolation receipt.
    output = {
        "schema": RESPONSE_SCHEMA,
        "status": "AUDIT_OBSERVED_UNSIGNED",
        "signed": False,
        "run_id": request.run_id,
        "container_id": request.container_id,
        "checks": checks,
    }
    response = json.dumps(output, sort_keys=True, separators=(",", ":")).encode("ascii")
    if len(response) > 4096:
        raise BrokerDenied("Unsigned observation exceeds bounded pipe response")
    return response


def serve_approved_request_once(approved: ApprovedActivation) -> None:
    """Operator-approved one-shot named pipe; no SCM provisioning."""
    from .audit_broker_windows import serve_once
    validate_service_identity(approved.policy, actual_sid=current_process_sid())
    store = DurableWindowsNonceStore()
    if not store.claim(approved.nonce, kind="operator"):
        raise BrokerDenied("Operator approval already consumed")
    serve_once(
        auditor_sid=approved.policy.auditor_sid,
        expected_service_sid=approved.policy.service_sid,
        forbidden_agent_sid=approved.policy.agent_sid,
        handler=lambda raw, peer: inspect_approved_run(
            raw, peer, approved, claim_nonce=lambda nonce: store.claim(
                nonce, kind="request",
            ),
        ),
    )
