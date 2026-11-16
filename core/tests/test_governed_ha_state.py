"""Home Assistant state read: inventory prerequisite, exact policy and no actuation."""
import asyncio
from types import SimpleNamespace
from dataclasses import replace

import pytest

from aura_core.application.governed_ha_state import (
    GovernedHomeAssistantStateReader, HomeStateDenied, HomeStateInvalid,
)
from aura_core.application.governed_home_inventory import HomeInventory, HomeDeviceHint
from aura_core.kernel.capabilities import CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType
from aura_core.kernel.permissions import AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry


def _inventory(*, available=True, provider_id="home.fake"):
    return HomeInventory(
        devices=(HomeDeviceHint("light.desk", "light", available),),
        provider_id=provider_id,
    )


class FakeHA:
    def __init__(self, payload=None):
        self.calls = []
        self.payload = payload

    async def list_tools(self):
        return (MCPTool(
            name="get_entity_state", description="Read one entity state only",
            input_schema={
                "type": "object",
                "properties": {"device_id": {"type": "string"}},
                "required": ["device_id"], "additionalProperties": False,
            },
        ),)

    async def call_tool(self, name, args):
        self.calls.append((name, dict(args)))
        return SimpleNamespace(
            is_error=False,
            structured_content=self.payload if self.payload is not None else {
                "device_id": "light.desk",
                "state": "on",
                "sampled_at": "2026-11-16T12:34:00Z",
            },
        )


def _system(*, allow=False, scope="home/entities/light.desk/read-only",
            payload=None, inventory=None):
    services = ServiceRegistry()
    service = services.register(ServiceDefinition(
        name="home-assistant-mcp", version="1.0.0",
        provider="mcp", category=ServiceCategory.MCP,
    ), object())
    providers = ProviderRegistry(services)
    fake = FakeHA(payload)
    providers.register(ProviderDefinition(
        provider_id="home.fake", name="Fake HA",
        version="1.0.0", service_id=service.service_id,
    ), fake)
    capabilities = CapabilityRegistry(services)
    capabilities.register(CapabilityDefinition(
        capability_id="home.entity.state.read",
        name="Home state reader", version="1.0.0",
        description="Scoped read-only HA entity state",
        provider_id="home.fake", provider_type=ProviderType.MCP,
        category=CapabilityCategory.AUTOMATION,
        tool_name="get_entity_state", risk_level="medium",
    ))
    engine = PermissionEngine(capabilities)
    if allow:
        engine.add_policy(PermissionPolicy(
            policy_id="owner.home.entity.read", policy_version="1.0.0",
            principal_id="trusted-owner",
            capability_id="home.entity.state.read",
            operation_id="home.entity.state.read",
            resource_scope=scope,
            authorization_level=AuthorizationLevel.READ,
            decision=AuthorizationDecision.ALLOW,
        ))
    reader = GovernedHomeAssistantStateReader(
        MCPGateway(capabilities, providers, engine),
        authenticated_principal_id="trusted-owner",
        authorized_inventory=_inventory() if inventory is None else inventory,
    )
    return reader, fake, engine


def _run(reader, device_id="light.desk"):
    return asyncio.run(reader.read(device_id=device_id))


def test_registered_gateway_approved_state_read_returns_bounded_untrusted_evidence():
    reader, provider, engine = _system(allow=True)
    result = _run(reader)
    assert (result.device_id, result.state, result.provider_id) == ("light.desk", "on", "home.fake")
    assert result.sampled_at == "2026-11-16T12:34:00+00:00"
    assert result.trust == "UNTRUSTED_STATE_METADATA"
    assert result.read_only is True
    assert provider.calls == [("get_entity_state", {"device_id": "light.desk"})]
    assert engine.audit_records()[-1].decision.decision is AuthorizationDecision.ALLOW
    assert not hasattr(reader, "turn_on") and not hasattr(reader, "unlock")


def test_default_deny_blocks_hardware_provider_before_dispatch():
    reader, provider, engine = _system()
    with pytest.raises(HomeStateDenied):
        _run(reader)
    assert provider.calls == []
    assert engine.audit_records()[0].decision.decision is AuthorizationDecision.DENY


def test_wrong_scope_cannot_read_same_device():
    reader, provider, _ = _system(allow=True, scope="home/entities/other/read-only")
    with pytest.raises(HomeStateDenied):
        _run(reader)
    assert provider.calls == []


def test_unknown_or_unavailable_device_denied_before_gateway_call():
    reader, fake, engine = _system(allow=True)
    with pytest.raises(HomeStateDenied):
        _run(reader, "light.unknown")
    reader_unavailable, fake2, engine2 = _system(allow=True, inventory=_inventory(available=False))
    with pytest.raises(HomeStateDenied):
        _run(reader_unavailable)
    assert fake.calls == fake2.calls == []
    assert engine.audit_records() == engine2.audit_records() == ()


@pytest.mark.parametrize("payload", [
    {"device_id": "light.desk", "state": "unlock", "sampled_at": "2026-11-16T12:34:00Z"},
    {"device_id": "camera.secret", "state": "on", "sampled_at": "2026-11-16T12:34:00Z"},
    {"device_id": "light.desk", "state": 1, "sampled_at": "2026-11-16T12:34:00Z"},
    {"device_id": "light.desk", "state": "on", "sampled_at": "yesterday"},
    {"device_id": "light.desk", "state": "on", "sampled_at": "2026-11-16T12:34:00"},
    {"status": "failed", "error": "PRIVATE_TOKEN"},
])
def test_malformed_or_action_like_state_fails_closed(payload):
    reader, provider, _ = _system(allow=True, payload=payload)
    with pytest.raises(HomeStateInvalid):
        _run(reader)
    assert len(provider.calls) == 1


def test_mismatched_provider_identity_rejected_after_independent_gateway_authorization():
    reader, provider, _ = _system(allow=True, inventory=_inventory(provider_id="other.provider"))
    with pytest.raises(HomeStateInvalid, match="does not match"):
        _run(reader)
    assert len(provider.calls) == 1


@pytest.mark.parametrize("device_id", ["", "../private", "camera/a", "a\nb", "x" * 65, None])
def test_invalid_device_identifier_never_dispatched(device_id):
    reader, provider, engine = _system(allow=True)
    with pytest.raises(ValueError):
        _run(reader, device_id)
    assert provider.calls == []
    assert engine.audit_records() == ()


def test_untrusted_forged_inventory_is_not_authority_and_fails_validation():
    reader, provider, _ = _system(allow=True)
    bad = _inventory()
    for value in (
        replace(bad, scope="home/admin"),
        replace(bad, provider_id="unsafe/provider"),
        replace(bad, read_only=False),
        replace(bad, devices=(HomeDeviceHint("../secret", "light", True),)),
        replace(bad, devices=(HomeDeviceHint("camera.secret", "camera", True),)),
        replace(bad, devices=()),
    ):
        if value.devices == ():
            # An empty authorized inventory is valid but cannot read a device.
            read_empty, _, _ = _system(allow=True, inventory=value)
            with pytest.raises(HomeStateDenied):
                _run(read_empty)
            continue
        with pytest.raises(ValueError):
            GovernedHomeAssistantStateReader(
                reader._gateway,
                authenticated_principal_id="trusted-owner",
                authorized_inventory=value,
            )


def test_no_override_for_principal_policy_or_inventory_in_read_method():
    reader, provider, _ = _system(allow=True)
    with pytest.raises(TypeError):
        asyncio.run(reader.read(device_id="light.desk", principal_id="admin"))
    with pytest.raises(TypeError):
        asyncio.run(reader.read(device_id="light.desk", operation_id="home.unlock"))
    assert provider.calls == []


def test_provider_errors_do_not_leak_home_secrets():
    reader, provider, _ = _system(allow=True)
    async def fail(name, args):
        raise RuntimeError("HASS_ACCESS_TOKEN=private")
    provider.call_tool = fail
    with pytest.raises(HomeStateInvalid) as exc:
        _run(reader)
    assert "private" not in str(exc.value)
