"""#57/#64: real Kernel CapabilityRegistry selection with no authority grants."""
from __future__ import annotations

import pytest

from aura_core.application.specialist_selection import (
    SpecialistProfile, suggest_registered_specialist,
)
from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType,
)
from aura_core.kernel.permissions import RiskLevel
from aura_core.kernel.services import ServiceRegistry


def capability(registry, *, provider, risk="low", name="public.search"):
    return registry.register(CapabilityDefinition(
        capability_id=name, name="Search", version="1.0",
        description="Public registry capability", provider_id=provider,
        provider_type=ProviderType.MCP, category=CapabilityCategory.RESEARCH,
        risk_level=risk,
    ))


def registry():
    result = CapabilityRegistry(ServiceRegistry())
    capability(result, provider="mcp.primary")
    capability(result, provider="mcp.backup")
    return result


def profiles():
    return (
        SpecialistProfile("research.primary", "researcher",
                          "public.search", "mcp.primary", priority=-2),
        SpecialistProfile("research.backup", "researcher",
                          "public.search", "mcp.backup", priority=0),
    )


def select(reg, specs=None, *, required="public.search",
           risk=RiskLevel.MEDIUM):
    return suggest_registered_specialist(
        registry=reg, profiles=profiles() if specs is None else specs,
        capability_id=required, risk_level=risk,
    )


def test_real_registry_provider_health_fallback_without_registering_new_tools():
    reg = registry()
    before = len(reg.records())
    primary = select(reg)
    assert primary.provider_id == "mcp.primary"
    assert primary.profile_id == "research.primary"
    assert primary.registry_availability_checked
    assert not primary.profile_identity_verified
    assert not primary.authorization_checked
    assert not primary.owner_approval_verified
    assert not primary.tool_invoked
    assert not primary.specialist_started

    reg.update_health("public.search", "mcp.primary", available=False, healthy=False)
    fallback = select(reg)
    assert fallback.provider_id == "mcp.backup"
    assert fallback.eligible_profiles_observed == 1
    assert len(reg.records()) == before


def test_all_providers_unavailable_fail_closed():
    reg = registry()
    for provider in ("mcp.primary", "mcp.backup"):
        reg.update_health("public.search", provider, available=False, healthy=False)
    with pytest.raises(LookupError):
        select(reg)


def test_unregistered_capability_or_unmatched_profiles_do_not_grant_authority():
    reg = registry()
    with pytest.raises(LookupError):
        select(reg, required="admin.root")
    with pytest.raises(LookupError):
        select(reg, specs=(SpecialistProfile(
            "coder.local", "coder", "another.capability", "mcp.primary",
        ),))


def test_high_risk_request_and_high_risk_provider_are_denied():
    reg = registry()
    with pytest.raises(PermissionError):
        select(reg, risk=RiskLevel.HIGH)
    with pytest.raises(PermissionError):
        select(reg, risk=RiskLevel.CRITICAL)
    only_high = CapabilityRegistry(ServiceRegistry())
    capability(only_high, provider="mcp.danger", risk="critical")
    with pytest.raises(PermissionError):
        select(
            only_high, specs=(SpecialistProfile(
                "danger", "coder", "public.search", "mcp.danger",
            ),),
        )


@pytest.mark.parametrize("bad", [
    SpecialistProfile("../root", "coder", "public.search", "mcp.primary"),
    SpecialistProfile("a", "root", "public.search", "mcp.primary"),
    SpecialistProfile("a", "coder", "unknown/capability", "mcp.primary"),
    SpecialistProfile("a", "coder", "public.search", "mcp.primary", priority=True),
    SpecialistProfile("a", "coder", "public.search", "mcp.primary", priority=21),
])
def test_invalid_role_or_capability_descriptor_rejected(bad):
    with pytest.raises(ValueError):
        select(registry(), specs=(bad,))


def test_duplicate_profile_identity_and_boolean_risk_fail_closed():
    reg = registry()
    with pytest.raises(ValueError, match="duplicate"):
        select(reg, specs=(profiles()[0], profiles()[0]))
    with pytest.raises(ValueError):
        select(reg, risk=True)
    with pytest.raises(ValueError):
        select(reg, specs=list(profiles()))


def test_stable_selection_order_independent_of_profile_listing():
    reg = registry()
    assert select(reg, specs=profiles()) == select(reg, specs=tuple(reversed(profiles())))
