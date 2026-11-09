"""F2.5 sealed IPC audit pipeline (INACTIVE until independent activation review).

All privileged Docker operations execute inside the broker Windows process:
the named-pipe transport supplies the real impersonated client SID, the
backend measures the Docker daemon, the SQLite store consumes a nonce, and
the broker key signs a *measurement* (not an isolation receipt).

The deployed F2.1 service deliberately remains deny_only and never calls
serve_signed_audit_once(). A future operator-reviewed *audit_only* activation
must first establish Windows service provisioning, a protected signing key,
and that neither agent nor AuraAuditor can access Docker directly.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .audit_broker_protocol import BrokerDenied
from .audit_broker_service import (
    BrokerServicePolicy, TRUST_ROOT, STATE_ROOT,
    preflight_service, validate_service_identity,
)
from .audit_broker_windows import current_process_sid, serve_once
from .audit_broker_docker import DockerAuditBackend
from .audit_broker_measurement import evaluate_broker_measurement
from .audit_broker_receipt import DurableNonceStore
from .audit_broker_topology import BrokerTopologyAudit
from .audit_broker_vm_executor import (
    PINNED_DISK, verify_sealed_vm_runtime,
)

BROKER_PRIVATE_KEY = TRUST_ROOT / "keys" / "broker-ed25519.pem"
BROKER_NONCE_DB = STATE_ROOT / "nonces.sqlite3"


def load_sealed_broker_key() -> Ed25519PrivateKey:
    """Read only an operator-created, broker-owned D: Ed25519 private key."""
    path = BROKER_PRIVATE_KEY
    if (not path.is_absolute() or path.is_symlink()
            or path.parent.is_symlink() or not path.parent.is_dir()
            or not path.is_file() or path.stat().st_size > 8192):
        raise BrokerDenied("Protected broker Ed25519 key has not been provisioned")
    from aura_core.evolution.windows_owner_storage import require_private_acl
    require_private_acl(path.parent)
    require_private_acl(path)
    key = load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise BrokerDenied("Broker has no independent Ed25519 signing key")
    return key


class BrokerAuditPipeline:
    """Broker-only IPC handler; never callable through AURA MCP Gateway.

    The runtime must use the separately activated audit_only policy. The
    shipped parser never permits that mode, so this is a code integration
    foundation rather than a live, enabled Windows service.
    """

    def __init__(
        self, *, policy: BrokerServicePolicy,
        topology: BrokerTopologyAudit,
        nonces: DurableNonceStore,
        signer: Ed25519PrivateKey,
        identity_source: Callable[[], str] = current_process_sid,
    ) -> None:
        if (type(policy) is not BrokerServicePolicy
                or policy.mode != "audit_only"
                or not isinstance(topology, BrokerTopologyAudit)
                or not isinstance(nonces, DurableNonceStore)
                or not isinstance(signer, Ed25519PrivateKey)):
            raise BrokerDenied("Broker signed measurements are not activated")
        self._policy = policy
        self._topology = topology
        self._nonces = nonces
        self._signer = signer
        self._identity_source = identity_source

    def handle(self, raw: bytes, peer_sid: str) -> bytes:
        validate_service_identity(
            self._policy, actual_sid=self._identity_source(),
        )
        return evaluate_broker_measurement(
            raw,
            peer_sid=peer_sid,
            auditor_sid=self._policy.auditor_sid,
            topology=self._topology,
            claim_nonce=self._nonces.claim,
            signer=self._signer,
        )


def build_sealed_audit_pipeline() -> BrokerAuditPipeline:
    """Assemble protected Docker/nonce/signature objects under broker SID.

    The current deny_only service always rejects this activation. It cannot
    be toggled via request JSON, environment variables or a CLI flag.
    """
    policy = preflight_service()
    if policy.mode != "audit_only":
        raise BrokerDenied("Signed broker audit not authorized by service policy")
    validate_service_identity(policy, actual_sid=current_process_sid())
    verify_sealed_vm_runtime()
    key = load_sealed_broker_key()
    nonces = DurableNonceStore(BROKER_NONCE_DB)
    backend = DockerAuditBackend()
    topology = BrokerTopologyAudit(
        backend=backend, pinned_vm_image=PINNED_DISK,
    )
    return BrokerAuditPipeline(
        policy=policy, topology=topology,
        nonces=nonces, signer=key,
    )


def serve_signed_audit_once(runtime: BrokerAuditPipeline) -> None:
    """Future service hook; unreachable through the shipped deny_only SCM."""
    if type(runtime) is not BrokerAuditPipeline:
        raise BrokerDenied("Untrusted or absent broker audit pipeline")
    validate_service_identity(
        runtime._policy, actual_sid=current_process_sid(),
    )
    if runtime._policy.mode != "audit_only":
        raise BrokerDenied("Broker signed audit not activated")
    serve_once(
        auditor_sid=runtime._policy.auditor_sid,
        expected_service_sid=runtime._policy.service_sid,
        forbidden_agent_sid=runtime._policy.agent_sid,
        handler=runtime.handle,
    )
