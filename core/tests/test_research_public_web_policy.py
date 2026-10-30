"""Research policy regression: actual Turkish directive -> Gateway -> MCP tool.

The provider is a deterministic local fake; no external SearxNG/network is
required to prove that a policy allows only the intended public-web scope.
"""
from __future__ import annotations

import asyncio

from aura_core.agent.runtime import AgentExecutor, Plan, PlanState, PlanStep, Task
from aura_core.application.directive_planner import DirectivePlanner
from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType,
)
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationRequest, PermissionEngine, PermissionPolicy,
    AuthorizationLevel, RiskLevel,
)
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry
from aura_core.research.config import ResearchMCPConfig
from aura_core.research.provider_bootstrap import install_local_research_policies


class FakeResearchProvider:
    def __init__(self):
        self.calls = []

    async def list_tools(self):
        return (
            MCPTool("search", "Search the web", {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            }),
            MCPTool("fetch", "Fetch public resource", {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
                "additionalProperties": False,
            }),
        )

    async def call_tool(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        return {"results": [{"title": "Example", "url": "https://example.org/"}]}


def setup():
    config = ResearchMCPConfig.from_env()
    services = ServiceRegistry()
    service = services.register(
        ServiceDefinition("research-test", "1", "mcp", ServiceCategory.MCP),
        object(),
    )
    capabilities = CapabilityRegistry(services)
    registry = ProviderRegistry(services)
    provider = FakeResearchProvider()
    registry.register(
        ProviderDefinition(config.provider_id, "Research Test", "1", service.service_id),
        provider,
    )
    for capability_id, tool in (
        (config.capability_id, config.search_tool_name),
        (config.fetch_capability_id, config.fetch_tool_name),
    ):
        capabilities.register(
            CapabilityDefinition(
                capability_id, tool, "1", "Governed public web research",
                config.provider_id, ProviderType.MCP, CapabilityCategory.RESEARCH,
                tool_name=tool, risk_level="medium",
            )
        )
    engine = PermissionEngine(capabilities)
    gateway = MCPGateway(capabilities, registry, engine)
    return config, engine, gateway, provider


def request(config, *, principal="local_owner", scope="public-web"):
    return MCPGatewayRequest(
        request_id="research-test",
        principal_id=principal,
        capability_id=config.capability_id,
        operation_id=config.search_operation_id,
        resource_scope=scope,
        risk_level=RiskLevel.LOW,
        tool_name=config.search_tool_name,
        arguments={"query": "Yapay zekadaki son gelişmeleri araştır"},
    )


def test_planner_scope_is_authorized_and_search_dispatches_through_gateway():
    config, engine, gateway, provider = setup()
    directive = "Bana yapay zeka alanında bu hafta dünyada yaşanan en son 3 önemli gelişmeyi araştırıp özetler misin?"
    generated = DirectivePlanner().plan(directive)
    assert generated.resource_scope == "public-web"
    assert generated.steps[0].capability_id == config.capability_id
    # No implicit grant: before installing an explicit policy the tool is denied.
    denied = asyncio.run(gateway.invoke(request(config)))
    assert denied.decision is AuthorizationDecision.DENY
    assert provider.calls == []

    install_local_research_policies(engine, config)
    steps = tuple(PlanStep(
        item.step_id, item.capability_id, item.operation_id,
        item.tool_name, item.risk_level, item.arguments,
        frozenset(item.depends_on), item.max_attempts,
    ) for item in generated.steps)
    task = Task("research-task", "local_owner", directive, generated.resource_scope)
    result = asyncio.run(AgentExecutor(gateway).execute(
        task, Plan("research-plan", task.task_id, steps)
    ))
    assert result.state is PlanState.SUCCEEDED
    assert provider.calls == [("search", {"query": directive})]


def test_grants_stay_principal_operation_and_scope_specific():
    config, engine, gateway, provider = setup()
    install_local_research_policies(engine, config)
    for kwargs in (
        {"principal": "other-user"},
        {"scope": "local_default"},
        {"scope": "private-files"},
    ):
        response = asyncio.run(gateway.invoke(request(config, **kwargs)))
        assert response.decision is AuthorizationDecision.DENY
    assert provider.calls == []

    fetch = MCPGatewayRequest(
        request_id="fetch-test", principal_id="local_owner",
        capability_id=config.fetch_capability_id,
        operation_id=config.fetch_operation_id, resource_scope="public-web",
        risk_level=RiskLevel.LOW, tool_name=config.fetch_tool_name,
        arguments={"url": "https://example.org/"},
    )
    response = asyncio.run(gateway.invoke(fetch))
    assert response.decision is AuthorizationDecision.ALLOW
    assert provider.calls == [("fetch", {"url": "https://example.org/"})]


def test_explicit_deny_overrides_public_web_allow():
    config, engine, gateway, provider = setup()
    install_local_research_policies(engine, config)
    engine.add_policy(PermissionPolicy(
        "test-explicit-deny", "1", "local_owner",
        config.capability_id, config.search_operation_id, "public-web",
        AuthorizationLevel.DENY, AuthorizationDecision.DENY,
    ))
    denied = asyncio.run(gateway.invoke(request(config)))
    assert denied.decision is AuthorizationDecision.DENY
    assert provider.calls == []
