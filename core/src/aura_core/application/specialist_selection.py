"""Registry-aware specialist PROFILE selection only; never tool dispatch.

Candidates are explicit caller-supplied descriptors, not authenticated agents.
Authoritative CapabilityRegistry health/state is consulted, but only
PermissionEngine and MCP Gateway may authorize execution.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from aura_core.kernel.capabilities import CapabilityRegistry, CapabilityState
from aura_core.kernel.permissions import RiskLevel

_ID = re.compile(r"[A-Za-z][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_ROLES = frozenset({"coder", "researcher"})


@dataclass(frozen=True, slots=True)
class SpecialistProfile:
    profile_id: str
    role: str
    capability_id: str
    provider_id: str
    priority: int = 0


@dataclass(frozen=True, slots=True)
class SpecialistSelection:
    profile_id: str
    role: str
    capability_id: str
    provider_id: str
    request_risk: RiskLevel
    eligible_profiles_observed: int
    registry_availability_checked: bool = True
    profile_identity_verified: bool = False
    authorization_checked: bool = False
    owner_approval_verified: bool = False
    tool_invoked: bool = False
    specialist_started: bool = False


def _id(value: str, name: str) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise ValueError(f"invalid {name}")
    return value


def suggest_registered_specialist(
    *, registry: CapabilityRegistry,
    profiles: tuple[SpecialistProfile, ...],
    capability_id: str,
    risk_level: RiskLevel = RiskLevel.MEDIUM,
) -> SpecialistSelection:
    """Find healthy registered low/medium-risk profile matching a provider.

    No new capability, registry entry, role, policy, tool or agent is created.
    Results are data proposals and cannot be used as Owner approval receipts.
    """
    if type(registry) is not CapabilityRegistry:
        raise ValueError("CapabilityRegistry required")
    capability = _id(capability_id, "capability")
    if type(risk_level) is not RiskLevel:
        raise ValueError("RiskLevel enum required")
    if risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
        raise PermissionError("high/critical specialist tasks need separate Owner authorization")
    if type(profiles) is not tuple or not 1 <= len(profiles) <= 32:
        raise ValueError("1..32 explicit specialist profiles required")
    seen: set[str] = set()
    validated: list[SpecialistProfile] = []
    for profile in profiles:
        if type(profile) is not SpecialistProfile:
            raise ValueError("SpecialistProfile required")
        profile_id = _id(profile.profile_id, "profile")
        _id(profile.capability_id, "profile capability")
        _id(profile.provider_id, "profile provider")
        if profile_id.casefold() in seen:
            raise ValueError("duplicate specialist profile identity")
        seen.add(profile_id.casefold())
        if type(profile.role) is not str or profile.role not in _ROLES:
            raise ValueError("unsupported specialist role")
        if type(profile.priority) is not int or not -20 <= profile.priority <= 20:
            raise ValueError("invalid profile priority")
        validated.append(profile)

    provider_records = registry.providers(capability)
    if not provider_records:
        raise LookupError("requested capability is not registered")
    available = {}
    high_risk_found = False
    for position, record in enumerate(provider_records):
        if (
            not record.available or not record.healthy
            or record.state not in {CapabilityState.AVAILABLE, CapabilityState.ACTIVE}
        ):
            continue
        if record.definition.risk_level in {"high", "critical"}:
            high_risk_found = True
            continue
        available[record.definition.provider_id] = position
    choices = [
        profile for profile in validated
        if profile.capability_id == capability
        and profile.provider_id in available
    ]
    if not choices:
        if high_risk_found:
            raise PermissionError("only high/critical capability providers are eligible")
        raise LookupError("no registered healthy specialist profile for capability")
    chosen = min(
        choices,
        key=lambda profile: (
            profile.priority,
            available[profile.provider_id],
            profile.profile_id,
        ),
    )
    return SpecialistSelection(
        profile_id=chosen.profile_id, role=chosen.role,
        capability_id=capability, provider_id=chosen.provider_id,
        request_risk=risk_level, eligible_profiles_observed=len(choices),
    )
