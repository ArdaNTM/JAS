"""Regression tests for AURA hardening and governed Nirvana MCP boundaries."""
from __future__ import annotations

import asyncio
import pytest

from aura_core.kernel.capabilities import CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType
from aura_core.kernel.events import EventBus
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, AuthorizationRequest,
    PermissionEngine, PermissionPolicy, RiskLevel,
)
from aura_core.kernel.services import ServiceRegistry, ServiceDefinition, ServiceCategory
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.enterprise.policy_bundle import PolicyBundle, PolicyEffect, PolicyRule
from aura_core.enterprise.runtime_controls import HashChainAuditLedger
from aura_core.mcp.graph_memory_provider import GraphMemoryMCPProvider
from aura_core.mcp.screen_control_provider import ScreenControlMCPProvider
from aura_core.application.swarm_orchestration import SwarmOrchestrator, SpecialistStep


def foundation(provider, cap_id, tool_name):
    events = EventBus()
    services = ServiceRegistry(events)
    caps = CapabilityRegistry(services, event_bus=events)
    providers = ProviderRegistry(services, event_bus=events)
    service = services.register(ServiceDefinition(
        name="provider", version="1.0.0", provider="test", category=ServiceCategory.MCP), provider)
    providers.register(ProviderDefinition(
        provider_id="test-provider", name="Test", version="1.0.0",
        service_id=service.service_id), provider)
    caps.register(CapabilityDefinition(
        capability_id=cap_id, name=tool_name, version="1.0.0", description="Test",
        provider_id="test-provider", provider_type=ProviderType.MCP,
        category=CapabilityCategory.MEMORY, tool_name=tool_name,
        risk_level="high" if cap_id == "ScreenControl" else "low"))
    return events, caps, providers


def policy(cap_id, decision):
    return PermissionPolicy(policy_id="policy", policy_version="1.0.0",
        principal_id="alice", capability_id=cap_id, operation_id=cap_id,
        resource_scope="local", authorization_level=AuthorizationLevel.EXECUTE,
        decision=decision)


def request(cap_id, tool, arguments):
    return MCPGatewayRequest(request_id="req-1", principal_id="alice",
        capability_id=cap_id, operation_id=cap_id, resource_scope="local",
        risk_level=RiskLevel.HIGH if cap_id == "ScreenControl" else RiskLevel.LOW,
        tool_name=tool, arguments=arguments)


def test_enterprise_approval_never_overrides_missing_or_local_deny():
    provider = GraphMemoryMCPProvider()
    events, caps, _ = foundation(provider, "memory.graph.query", "graph_memory_query")
    bundle = PolicyBundle(version="v1", rules=(PolicyRule(
        rule_id="one", principal_id="alice", capability_id="memory.graph.query",
        operation_id="memory.graph.query", resource_scope="local",
        effect=PolicyEffect.REQUIRE_APPROVAL),))
    engine = PermissionEngine(caps, event_bus=events, policy_bundle=bundle)
    auth = AuthorizationRequest(request_id="a", principal_id="alice",
        capability_id="memory.graph.query", operation_id="memory.graph.query",
        resource_scope="local", risk_level=RiskLevel.LOW)
    assert engine.authorize(auth).decision == AuthorizationDecision.DENY
    engine.add_policy(policy("memory.graph.query", AuthorizationDecision.DENY))
    assert engine.authorize(auth).decision == AuthorizationDecision.DENY


def test_enterprise_approval_with_local_allow_requires_approval():
    provider = GraphMemoryMCPProvider()
    events, caps, _ = foundation(provider, "memory.graph.query", "graph_memory_query")
    bundle = PolicyBundle(version="v1", rules=(PolicyRule(
        rule_id="one", principal_id="alice", capability_id="memory.graph.query",
        operation_id="memory.graph.query", resource_scope="local",
        effect=PolicyEffect.REQUIRE_APPROVAL),))
    engine = PermissionEngine(caps, event_bus=events, policy_bundle=bundle)
    engine.add_policy(policy("memory.graph.query", AuthorizationDecision.ALLOW))
    auth = AuthorizationRequest(request_id="a", principal_id="alice",
        capability_id="memory.graph.query", operation_id="memory.graph.query",
        resource_scope="local", risk_level=RiskLevel.LOW)
    assert engine.authorize(auth).decision == AuthorizationDecision.REQUIRE_APPROVAL


def test_provider_valueerror_is_propagated_and_publishes_failure():
    class Provider:
        async def list_tools(self):
            from aura_core.mcp.mcp_provider import MCPTool
            return (MCPTool("graph_memory_query", "Query",
                {"type":"object","properties":{},"additionalProperties":True}),)
        async def call_tool(self, name, arguments=None):
            raise ValueError("provider runtime error")
    events, caps, providers = foundation(Provider(), "memory.graph.query", "graph_memory_query")
    ledger = HashChainAuditLedger()
    engine = PermissionEngine(caps)
    engine.add_policy(policy("memory.graph.query", AuthorizationDecision.ALLOW))
    gateway = MCPGateway(caps, providers, engine, event_bus=events, audit_ledger=ledger)
    with pytest.raises(ValueError, match="provider runtime error"):
        asyncio.run(gateway.invoke(request("memory.graph.query", "graph_memory_query", {})))
    assert ledger.snapshot()[-1].outcome == "unknown"
    assert ledger.verify()
    assert events.snapshot()["published_total"] > 0


def test_graph_provider_requires_gateway_and_is_principal_scoped():
    provider = GraphMemoryMCPProvider()
    with pytest.raises(PermissionError):
        asyncio.run(provider.call_tool("graph_memory_insert", {
            "subject": "s", "predicate": "p", "object": "o"}))


def test_screen_control_always_requires_consumed_approval():
    provider = ScreenControlMCPProvider()
    with pytest.raises(PermissionError):
        asyncio.run(provider.call_tool("screen_control", {"action": "click", "x": 1, "y": 1}))


def test_swarm_never_dispatches_without_permission():
    provider = GraphMemoryMCPProvider()
    events, caps, providers = foundation(provider, "memory.graph.query", "graph_memory_query")
    gateway = MCPGateway(caps, providers, PermissionEngine(caps), event_bus=events)
    swarm = SwarmOrchestrator(gateway=gateway, event_bus=events)
    result = asyncio.run(swarm.execute(principal_id="alice", task_id="t1",
        steps=(SpecialistStep(role="researcher", capability_id="memory.graph.query",
            operation_id="memory.graph.query", resource_scope="local",
            tool_name="graph_memory_query", arguments={"subject":"s"}),)))
    assert result[0].decision == AuthorizationDecision.DENY
