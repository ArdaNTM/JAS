"""Authorized home device discovery: real Core Gateway, safe metadata and no actuation."""
import asyncio
from types import SimpleNamespace

import pytest

from aura_core.application.governed_home_inventory import (
    GovernedHomeInventoryReader, HomeInventoryDenied, HomeInventoryInvalid,
)
from aura_core.kernel.capabilities import CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType
from aura_core.kernel.permissions import AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry


def _devices():
    return [
        {"device_id": "switch.office", "category": "switch", "available": False},
        {"device_id": "light.desk", "category": "light", "available": True},
    ]


class FakeHomeMCP:
    def __init__(self, result=None):
        self.calls = []
        self.result = result

    async def list_tools(self):
        return (MCPTool(
            name="list_devices", description="Read-only home inventory",
            input_schema={"type": "object", "additionalProperties": False},
        ),)

    async def call_tool(self, name, args):
        self.calls.append((name, dict(args)))
        return SimpleNamespace(
            is_error=False,
            structured_content={"devices": _devices()} if self.result is None else self.result,
        )


def _system(*, allow=False, scope="home/devices/read-only", result=None):
    services = ServiceRegistry()
    service = services.register(ServiceDefinition(
        name="Home MCP", version="1.0.0", provider="mcp",
        category=ServiceCategory.MCP,
    ), object())
    providers = ProviderRegistry(services)
    fake = FakeHomeMCP(result)
    providers.register(ProviderDefinition(
        provider_id="home.fake", name="Test Home",
        version="1.0.0", service_id=service.service_id,
    ), fake)
    capabilities = CapabilityRegistry(services)
    capabilities.register(CapabilityDefinition(
        capability_id="home.device.discover", name="Home device inventory",
        version="1.0.0", description="Read-only discovery",
        provider_id="home.fake", provider_type=ProviderType.MCP,
        category=CapabilityCategory.AUTOMATION, tool_name="list_devices",
        risk_level="medium",
    ))
    engine = PermissionEngine(capabilities)
    if allow:
        engine.add_policy(PermissionPolicy(
            policy_id="trusted-owner.home.read", policy_version="1.0.0",
            principal_id="trusted-owner", capability_id="home.device.discover",
            operation_id="home.device.discover", resource_scope=scope,
            authorization_level=AuthorizationLevel.READ,
            decision=AuthorizationDecision.ALLOW,
        ))
    gateway = MCPGateway(capabilities, providers, engine)
    return GovernedHomeInventoryReader(gateway, authenticated_principal_id="trusted-owner"), fake, engine


def _run(reader):
    return asyncio.run(reader.discover())


def test_read_only_registered_gateway_returns_bounded_sorted_inventory():
    reader, provider, engine = _system(allow=True)
    inventory = _run(reader)
    assert [d.device_id for d in inventory.devices] == ["light.desk", "switch.office"]
    assert [d.available for d in inventory.devices] == [True, False]
    assert all(d.trust == "UNTRUSTED_DEVICE_METADATA" for d in inventory.devices)
    assert inventory.read_only is True and inventory.scope == "home/devices/read-only"
    assert provider.calls == [("list_devices", {})]
    assert engine.audit_records()[-1].decision.decision is AuthorizationDecision.ALLOW
    assert not hasattr(reader, "turn_on")
    assert not hasattr(reader, "unlock")


def test_default_deny_blocks_provider_before_discovery():
    reader, fake, engine = _system()
    with pytest.raises(HomeInventoryDenied):
        _run(reader)
    assert fake.calls == []
    assert engine.audit_records()[0].decision.decision is AuthorizationDecision.DENY


def test_wrong_resource_scope_policy_never_authorizes():
    reader, fake, engine = _system(allow=True, scope="home/devices/other")
    with pytest.raises(HomeInventoryDenied):
        _run(reader)
    assert fake.calls == []


@pytest.mark.parametrize("payload", [
    {"devices": "not-a-list"},
    {"devices": [0]},
    {"devices": [{"device_id": "door.lock", "category": "lock", "available": True}]},
    {"devices": [{"device_id": "camera.secret", "category": "camera", "available": True}]},
    {"devices": [{"device_id": "../secrets", "category": "light", "available": True}]},
    {"devices": [{"device_id": "x\nowner", "category": "light", "available": True}]},
    {"devices": [{"device_id": "light.good", "category": "light", "available": 1}]},
    {"devices": [{"device_id": "same", "category": "light", "available": True}] * 2},
    {"devices": [{"device_id": "x" + str(i), "category": "sensor", "available": True} for i in range(65)]},
    {"status": "failed", "devices": []},
])
def test_unsafe_or_unbounded_provider_metadata_fails_closed(payload):
    reader, fake, _ = _system(allow=True, result=payload)
    with pytest.raises(HomeInventoryInvalid):
        _run(reader)
    assert len(fake.calls) == 1


def test_empty_inventory_is_safe_and_not_auto_enrollment():
    reader, fake, _ = _system(allow=True, result={"devices": []})
    inventory = _run(reader)
    assert inventory.devices == ()
    assert inventory.provider_id == "home.fake"


def test_no_client_supplied_principal_or_resource_scope():
    reader, fake, _ = _system(allow=True)
    with pytest.raises(TypeError):
        asyncio.run(reader.discover(principal_id="another"))
    with pytest.raises(TypeError):
        asyncio.run(reader.discover(resource_scope="home/admin"))
    assert fake.calls == []


def test_constructor_requires_existing_gateway_and_trusted_principal():
    reader, fake, _ = _system(allow=True)
    with pytest.raises(TypeError):
        GovernedHomeInventoryReader(object(), authenticated_principal_id="trusted-owner")
    for value in ("", " owner", "admin\nuser", "a" * 129, "\ud800"):
        with pytest.raises(ValueError):
            GovernedHomeInventoryReader(reader._gateway, authenticated_principal_id=value)


def test_provider_error_does_not_leak_secret_config():
    reader, fake, _ = _system(allow=True)
    async def fail(name, args):
        raise RuntimeError("ha_api_token=secret-private-value")
    fake.call_tool = fail
    with pytest.raises(HomeInventoryInvalid) as exc:
        _run(reader)
    assert "secret-private-value" not in str(exc.value)
