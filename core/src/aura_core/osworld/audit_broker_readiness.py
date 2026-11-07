"""Stage F2.6 read-only Windows host readiness evidence.

This module is intentionally NOT an attestation authority: its outputs are
unsigned, per-token diagnostics and can be copied or falsified. Never use
them to change the deny_only policy, authorize VM execution or issue a host
ISOLATION_SIGNED receipt.

Run the operator CLI independently under the actual AURA agent, AuraAuditor
and dedicated broker logons. The broker inspection additionally checks the
SCM service registration, protected deployment, and sealed VM runtime.
It never changes accounts, Docker permissions, NTFS ACLs, service state or
private keys.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .audit_broker_protocol import BrokerDenied
from .audit_broker_boundary import (
    DaemonPipeObservation,
    inspect_current_principal,
    _validate_observation,
)
from .audit_broker_service import (
    BrokerServicePolicy, load_service_policy, preflight_service,
    validate_service_identity,
)
from .audit_broker_scm_identity import verify_registered_service_account
from .audit_broker_vm_executor import verify_sealed_vm_runtime

REQUIRED_ACCESS = {
    "agent": "denied",
    "auditor": "denied",
    "broker": "allowed",
}


@dataclass(frozen=True, slots=True)
class HostReadinessObservation:
    role: str
    principal_sid: str
    daemon_access: str
    service_identity_checked: bool
    sealed_runtime_checked: bool
    signed: bool = False
    status: str = "OBSERVATION_ONLY"

    def __post_init__(self) -> None:
        if self.signed is not False or self.status != "OBSERVATION_ONLY":
            raise BrokerDenied("Readiness observations are never signed receipts")


def _check_broker_prerequisites(expected_sid: str) -> None:
    """Run only under the pinned broker token, not a mutable agent checkout.

    Real service preflight already enforces the pinned D: runtime and Docker
    access. The other two assertions ensure SCM registration and the sealed
    OSWorld source/interpreter/disk are independently checked. We DO NOT read
    a private signing key or create a replay database during readiness.
    """
    policy = preflight_service()
    validate_service_identity(policy, actual_sid=expected_sid)
    if policy.mode != "deny_only":
        raise BrokerDenied("F2.6 cannot activate the broker from a readiness probe")
    verify_registered_service_account(policy)
    verify_sealed_vm_runtime()


def inspect_role_readiness(
    *,
    role: str,
    expected_sid: str,
    sid_source: Callable[[], str] | None = None,
    access_probe: Callable[[], tuple[str, int | None]] | None = None,
    broker_prerequisites: Callable[[str], None] | None = None,
) -> HostReadinessObservation:
    """Return only an unsigned, OS-token-local diagnostic.

    An agent calling this function cannot attest a different account, and
    returned dictionaries or JSON are NEVER fed to broker/host signing.
    """
    if type(role) is not str or role not in REQUIRED_ACCESS:
        raise BrokerDenied("Unknown F2.6 Windows account role")
    observed = inspect_current_principal(
        role=role, expected_sid=expected_sid,
        sid_source=sid_source, access_probe=access_probe,
    )
    _validate_observation(observed)
    if observed.access != REQUIRED_ACCESS[role]:
        raise BrokerDenied("Windows Docker daemon access is not separated")
    if role == "broker":
        checker = _check_broker_prerequisites if broker_prerequisites is None else broker_prerequisites
        checker(expected_sid)
    return HostReadinessObservation(
        role=role, principal_sid=observed.principal_sid,
        daemon_access=observed.access,
        service_identity_checked=role == "broker",
        sealed_runtime_checked=role == "broker",
    )
