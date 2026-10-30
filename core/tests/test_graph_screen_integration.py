"""Durable GraphRAG and explicitly approved Windows ScreenControl regressions."""
from __future__ import annotations

import asyncio

import pytest

from aura_core.application.windows_screen_driver import WindowsDesktopInputDriver
from aura_core.enterprise.approval_store import ApprovalStatus, SQLiteApprovalStore
from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType,
)
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy,
    RiskLevel,
)
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry
from aura_core.mcp.screen_control_provider import ScreenControlMCPProvider
from aura_core.memory.graph_store import SQLiteGraphStore


def test_sqlite_graph_survives_reopen_and_isolated_two_hop_query(tmp_path):
    path = tmp_path / "graph.db"

    async def scenario():
        store = SQLiteGraphStore(path)
        a = await store.insert(principal_id="alice", subject="A", predicate="related", object="B")
        b = await store.insert(principal_id="alice", subject="B", predicate="related", object="C")
        await store.insert(principal_id="bob", subject="A", predicate="private", object="SECRET")
        assert len(await store.query(principal_id="alice", subject="A", depth=1)) == 1
        assert len(await store.query(principal_id="alice", subject="A", depth=2)) == 2
        assert await store.query(principal_id="charlie", subject="A") == []
        assert (await store.query(principal_id="alice", subject="A", depth=2))[0]["fact_id"] == a
        await store.close()
        reopened = SQLiteGraphStore(path)
        result = await reopened.query(principal_id="alice", subject="A", depth=2)
        assert {item["fact_id"] for item in result} == {a, b}
        assert all(item["untrusted"] for item in result)
        assert all(item["object"] != "SECRET" for item in result)

    asyncio.run(scenario())


class FakeUser32:
    def __init__(self):
        self.events = []
        self.cursor = None

    def GetSystemMetrics(self, index):
        return 1920 if index == 0 else 1080

    def SetCursorPos(self, x, y):
        self.cursor = (x, y)
        return 1

    def SendInput(self, number, event, size):
        self.events.append((number, size))
        return 1


def test_windows_input_driver_dispatches_bounded_real_win32_api_shape():
    async def scenario():
        user32 = FakeUser32()
        driver = WindowsDesktopInputDriver(user32=user32)
        await driver.click(10, 20)
        await driver.type_text("Hello")
        await driver.press_key("enter")
        assert user32.cursor == (10, 20)
        assert len(user32.events) == 14
        with pytest.raises(ValueError):
            await driver.click(9999, 20)
        with pytest.raises(ValueError):
            await driver.press_key("f12")
        with pytest.raises(ValueError):
            await driver.type_text("bad\ncommand")
    asyncio.run(scenario())


def test_gateway_screen_control_consumed_approval_is_required(tmp_path):
    class Driver:
        def __init__(self):
            self.clicks = []

        async def click(self, x, y):
            self.clicks.append((x, y))

    async def scenario():
        driver = Driver()
        provider = ScreenControlMCPProvider(input_driver=driver)
        services = ServiceRegistry()
        record = services.register(ServiceDefinition(
            name="screen", version="1", provider="test", category=ServiceCategory.MCP), provider)
        caps = CapabilityRegistry(services)
        providers = ProviderRegistry(services)
        providers.register(ProviderDefinition(provider_id="screen", name="Screen", version="1",
            service_id=record.service_id), provider)
        caps.register(CapabilityDefinition(
            capability_id="ScreenControl", name="Screen", version="1",
            description="Test", provider_id="screen", provider_type=ProviderType.MCP,
            category=CapabilityCategory.AUTOMATION,
            tool_name="screen_control", risk_level="high"))
        permissions = PermissionEngine(caps)
        args = {"action": "click", "x": 10, "y": 20}
        request = MCPGatewayRequest(
            request_id="screen-request", principal_id="alice", capability_id="ScreenControl",
            operation_id="ScreenControl", resource_scope="local",
            risk_level=RiskLevel.HIGH, tool_name="screen_control", arguments=args)
        permissions.add_policy(PermissionPolicy(
            policy_id="interactive-screen", policy_version="1",
            principal_id="alice", capability_id="ScreenControl",
            operation_id="ScreenControl", resource_scope="local",
            authorization_level=AuthorizationLevel.USER_APPROVAL_REQUIRED,
            decision=AuthorizationDecision.REQUIRE_APPROVAL))
        with SQLiteApprovalStore(str(tmp_path / "approvals.db")) as store:
            gateway = MCPGateway(caps, providers, permissions,
                approval_store=store, approval_fingerprint_key=b"k" * 32)
            pending = await gateway.invoke(request)
            assert pending.decision is AuthorizationDecision.REQUIRE_APPROVAL
            assert pending.approval_id and not driver.clicks
            record = store.get(pending.approval_id)
            approved = store.decide(record.approval_id, expected_version=record.version,
                approver_id="human:test", decision=ApprovalStatus.APPROVED)
            from dataclasses import replace
            executed = await gateway.invoke(replace(request, approval_id=approved.approval_id))
            assert executed.decision is AuthorizationDecision.ALLOW
            assert driver.clicks == [(10, 20)]
            replay = await gateway.invoke(replace(request, approval_id=approved.approval_id))
            assert replay.decision is AuthorizationDecision.REQUIRE_APPROVAL
            assert driver.clicks == [(10, 20)]

    asyncio.run(scenario())
