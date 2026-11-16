"""Real Core registry and PermissionEngine integrity tests; no new dispatch authority."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from aura_core.enterprise.core_integrity import (
    CoreRegistryState, GuardedMCPGateway, attest_core_registries, verify_core_registries,
)
from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityDefinition, CapabilityRegistry, CapabilityState, ProviderType,
)
from aura_core.kernel.events import EventBus
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionEngine,
    PermissionPolicy, RiskLevel,
)
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry, ServiceState
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry

_KEY = bytes(range(32))
_OTHER_KEY = bytes(range(1, 33))


class FakeMCPProvider:
    def __init__(self):
        self.calls = []

    async def list_tools(self):
        return (MCPTool(
            name="search", description="test-only",
            input_schema={
                "type": "object", "properties": {"query": {"type": "string"}},
                "required": ["query"], "additionalProperties": False,
            },
        ),)

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {"results": []}


def _objects():
    services = ServiceRegistry()
    service = services.register(ServiceDefinition(
        name="test-research", version="1.0.0", provider="mcp", category=ServiceCategory.MCP,
    ), object())
    providers = ProviderRegistry(services)
    provider = FakeMCPProvider()
    providers.register(ProviderDefinition(
        provider_id="research.fake", name="research", version="1.0.0",
        service_id=service.service_id,
    ), provider)
    capabilities = CapabilityRegistry(services)
    capabilities.register(CapabilityDefinition(
        capability_id="internet.search", name="Public research",
        version="1.0.0", description="Governed search",
        provider_id="research.fake", provider_type=ProviderType.MCP,
        category=CapabilityCategory.RESEARCH,
        risk_level="medium", tool_name="search",
    ))
    engine = PermissionEngine(capabilities)
    gateway = MCPGateway(capabilities, providers, engine)
    state = CoreRegistryState(services, providers, capabilities, engine)
    return services, providers, capabilities, engine, gateway, state, provider, service.service_id


def _policy(*, id="allow", decision=AuthorizationDecision.ALLOW,
            authorization_level=AuthorizationLevel.READ):
    return PermissionPolicy(
        policy_id=id, policy_version="1.0.0", principal_id="owner",
        capability_id="internet.search", operation_id="internet.search",
        resource_scope="public-web", decision=decision,
        authorization_level=authorization_level,
    )


def _request():
    return MCPGatewayRequest(
        request_id="integrity-test-001", principal_id="owner",
        capability_id="internet.search", operation_id="internet.search",
        resource_scope="public-web", tool_name="search",
        arguments={"query": "public evidence"},
        risk_level=RiskLevel.MEDIUM,
    )


def _guard(gateway, state, bus=None):
    receipt = attest_core_registries(state, key=_KEY, scope="owner-aura")
    return GuardedMCPGateway(
        gateway, state, receipt, key=_KEY, scope="owner-aura", event_bus=bus,
    )


def test_valid_external_receipt_does_not_include_policy_principals():
    services, providers, capabilities, engine, gateway, state, provider, _ = _objects()
    engine.add_policy(_policy())
    receipt = attest_core_registries(state, key=_KEY, scope="owner-aura")
    assert verify_core_registries(state, receipt, key=_KEY, scope="owner-aura")
    assert "owner" not in repr(receipt)
    assert "internet.search" not in repr(receipt)
    assert len(receipt.mac) == 64
    assert state.digest() == state.digest()


def test_guard_forwards_unchanged_request_to_existing_gateway_and_policy_only():
    _, _, _, engine, gateway, state, provider, _ = _objects()
    engine.add_policy(_policy())
    response = asyncio.run(_guard(gateway, state).invoke(_request()))
    assert response.decision is AuthorizationDecision.ALLOW
    assert provider.calls == [("search", {"query": "public evidence"})]
    assert engine.audit_records()[-1].decision.decision is AuthorizationDecision.ALLOW


def test_guard_does_not_grant_default_denied_gateway_request():
    _, _, _, engine, gateway, state, provider, _ = _objects()
    response = asyncio.run(_guard(gateway, state).invoke(_request()))
    assert response.decision is AuthorizationDecision.DENY
    assert provider.calls == []
    assert engine.audit_records()[-1].decision.decision is AuthorizationDecision.DENY


def test_policy_drift_denies_before_provider_and_emits_redacted_event():
    _, _, _, engine, gateway, state, provider, _ = _objects()
    engine.add_policy(_policy())
    bus = EventBus()
    observed = []
    bus.subscribe("CoreIntegrityRejected", lambda event: observed.append(event))
    wrapper = _guard(gateway, state, bus)
    engine.add_policy(_policy(id="extra-unexpected", decision=AuthorizationDecision.ALLOW))
    result = asyncio.run(wrapper.invoke(_request()))
    assert result.decision is AuthorizationDecision.DENY
    assert provider.calls == []
    assert engine.audit_records() == ()  # rejected before Gateway dispatch
    assert asyncio.run(bus.dispatch_once()) is True
    assert observed[0].payload["reason_code"] == "registry_or_policy_drift"
    assert "arguments" not in observed[0].payload
    assert "public evidence" not in str(observed[0].payload)


def test_registry_health_or_state_mutation_invalidates_receipt():
    services, providers, capabilities, engine, gateway, state, provider, sid = _objects()
    engine.add_policy(_policy())
    attestation = attest_core_registries(state, key=_KEY, scope="owner-aura")
    providers.update_health("research.fake", available=False, healthy=False)
    assert not verify_core_registries(state, attestation, key=_KEY, scope="owner-aura")
    providers.update_health("research.fake", available=True, healthy=True)
    assert verify_core_registries(state, attestation, key=_KEY, scope="owner-aura")
    capabilities.update_state("internet.search", "research.fake", CapabilityState.REVOKED)
    assert not verify_core_registries(state, attestation, key=_KEY, scope="owner-aura")
    capabilities.update_state("internet.search", "research.fake", CapabilityState.AVAILABLE)
    services.update_state(sid, ServiceState.FAILED)
    assert not verify_core_registries(state, attestation, key=_KEY, scope="owner-aura")


def test_policy_revocation_and_condition_mutation_change_deterministic_digest():
    _, _, _, engine, gateway, state, provider, _ = _objects()
    engine.add_policy(_policy())
    before = engine.integrity_digest()
    engine.revoke_policy("allow")
    assert engine.integrity_digest() != before
    receipt = attest_core_registries(state, key=_KEY, scope="owner-aura")
    engine.add_policy(_policy(id="later"))
    assert not verify_core_registries(state, receipt, key=_KEY, scope="owner-aura")


@pytest.mark.parametrize("badkey", [b"", b"short", "not-bytes", None])
def test_attestation_rejects_weak_or_missing_keys(badkey):
    *_, state, provider, sid = _objects()
    with pytest.raises(ValueError):
        attest_core_registries(state, key=badkey, scope="owner-aura")


def test_scope_key_and_forged_receipts_fail_closed():
    _, _, _, engine, gateway, state, _, _ = _objects()
    receipt = attest_core_registries(state, key=_KEY, scope="owner-aura")
    assert not verify_core_registries(state, receipt, key=_OTHER_KEY, scope="owner-aura")
    assert not verify_core_registries(state, receipt, key=_KEY, scope="another-aura")
    assert not verify_core_registries(state, replace(receipt, mac="f" * 64), key=_KEY, scope="owner-aura")
    assert not verify_core_registries(state, replace(receipt, registry_digest="x" * 64), key=_KEY, scope="owner-aura")


def test_require_approval_policy_still_defers_to_original_gateway():
    _, _, _, engine, gateway, state, provider, _ = _objects()
    engine.add_policy(_policy(authorization_level=AuthorizationLevel.USER_APPROVAL_REQUIRED))
    response = asyncio.run(_guard(gateway, state).invoke(_request()))
    assert response.decision is AuthorizationDecision.REQUIRE_APPROVAL
    assert provider.calls == []


def test_missing_or_invalid_guard_configuration_fails_closed():
    _, _, _, engine, gateway, state, provider, _ = _objects()
    receipt = attest_core_registries(state, key=_KEY, scope="owner-aura")
    with pytest.raises(ValueError):
        GuardedMCPGateway(gateway, state, receipt, key=b"tiny", scope="owner-aura")
    with pytest.raises(TypeError):
        GuardedMCPGateway(object(), state, receipt, key=_KEY, scope="owner-aura")
    with pytest.raises(ValueError):
        attest_core_registries(state, key=_KEY, scope="a\nspoof")
