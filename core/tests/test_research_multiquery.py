"""Multi-query evidence proof using real MCP Gateway and fail-closed fakes."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType,
)
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy, RiskLevel,
)
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.mcp.gateway import MCPGateway, MCPGatewayResponse
from aura_core.mcp.mcp_provider import MCPProvider
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry
from aura_core.research.mcp_source import MCPResearchSource
from aura_core.research.multiquery import (
    MultiQueryResearch, ResearchAuthorizationError, ResearchResponseError,
)


def _hit(url="https://docs.python.org/3/", *, rank=1):
    return {"title": "Documentation", "url": url, "snippet": "A documented source", "rank": rank}


def _payload(url="https://docs.python.org/3/", *, results=None):
    return {"backend": "searxng", "results": results if results is not None else [_hit(url)]}


def _response(payload=None, decision=AuthorizationDecision.ALLOW):
    return MCPGatewayResponse(
        decision=decision, result=SimpleNamespace(
            structured_content=payload if payload is not None else _payload(),
            is_error=False,
        ),
        provider_id="research.mcp", tool_name="search", reason="governed",
    )


class SpyGateway:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def invoke(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


def _spec():
    return SimpleNamespace(
        search_capability_id="internet.search",
        search_operation_id="internet.search",
        search_tool_name="search",
    )


def _runner(gateway):
    return MultiQueryResearch(MCPResearchSource(gateway, _spec()))


def _run(runner, queries=("first",), *, principal="local_owner"):
    return asyncio.run(runner.search(
        list(queries), principal_id=principal, resource_scope="public-web",
        risk_level=RiskLevel.MEDIUM, task_id="research-task",
    ))


def test_multiple_query_results_are_deduplicated_and_each_has_unique_gateway_audit_id():
    gateway = SpyGateway([
        _response(_payload(results=[_hit("https://example.org/a"), _hit("https://example.org/b", rank=2)])),
        _response(_payload(results=[_hit("https://example.org/a#fragment"), _hit("https://example.org/c", rank=2)])),
    ])
    evidence = _run(_runner(gateway), ("first", "second"))
    assert evidence.searched_count == 2
    assert len(evidence.results) == 3
    assert [hit.url for hit in evidence.results] == [
        "https://example.org/a", "https://example.org/b", "https://example.org/c",
    ]
    assert all(len(hit.url_sha256) == 64 for hit in evidence.results)
    assert [req.request_id for req in gateway.requests] == [
        "research-task:query:1:search", "research-task:query:2:search",
    ]
    assert all(req.capability_id == "internet.search" and req.tool_name == "search"
               and req.arguments.get("query") in ("first", "second") for req in gateway.requests)


@pytest.mark.parametrize("decision", [
    AuthorizationDecision.DENY, AuthorizationDecision.DEFER,
    AuthorizationDecision.REQUIRE_APPROVAL,
])
def test_authorization_denials_never_expose_partial_results(decision):
    gateway = SpyGateway([_response(), _response(decision=decision)])
    with pytest.raises(ResearchAuthorizationError):
        _run(_runner(gateway), ("first", "second"))
    assert len(gateway.requests) == 2


@pytest.mark.parametrize("bad", [
    "", "   ", "x" * 257, "hello\nsecond", None,
])
def test_invalid_queries_rejected_before_any_gateway_dispatch(bad):
    gateway = SpyGateway([])
    with pytest.raises(ValueError):
        _run(_runner(gateway), (bad,))
    assert gateway.requests == []


def test_duplicate_queries_rejected_before_gateway_dispatch():
    gateway = SpyGateway([])
    with pytest.raises(ValueError, match="duplicate"):
        _run(_runner(gateway), (" hello   world ", "HELLO WORLD"))
    assert gateway.requests == []


@pytest.mark.parametrize("uri", [
    "file:///etc/passwd", "http://127.0.0.1/admin",
    "http://10.0.0.1/", "http://[::1]/",
    "https://user:password@example.org/",
    "http://localhost/", "http://router.local/",
    "http://intranet/", "https://example.org:999999/",
    "https://example.org/\nHeader: X",
])
def test_unsafe_metadata_links_do_not_escape_validated_response(uri):
    with pytest.raises(ResearchResponseError):
        _run(_runner(SpyGateway([_response(_payload(results=[_hit(uri)]))])))


@pytest.mark.parametrize("bad_result", [
    {"status": "failed", "error": "MCP tool execution failed"},
    {"backend": "searxng", "results": "not-a-list"},
    {"backend": "searxng", "results": [_hit()] * 11},
    {"backend": "searxng", "results": [{"url": "https://example.org/"}]},
    {"backend": "searxng", "results": [_hit(rank=True)]},
    {"backend": "searxng", "results": [_hit(rank=11)]},
    {"backend": "searxng", "results": [_hit()] + [123]},
])
def test_invalid_provider_results_fail_closed(bad_result):
    with pytest.raises(ResearchResponseError):
        _run(_runner(SpyGateway([_response(bad_result)])))


def test_provider_invocation_failure_is_sanitized():
    class Broken:
        async def invoke(self, request):
            raise RuntimeError("secret-provider-internals")
    with pytest.raises(ResearchResponseError) as captured:
        _run(_runner(Broken()))
    assert "secret-provider-internals" not in str(captured.value)


def test_total_output_is_bounded_but_each_search_is_authorized():
    rows = [_hit(f"https://example.org/{n}", rank=n + 1) for n in range(10)]
    gateway = SpyGateway([_response(_payload(results=rows)), _response(_payload(results=rows[:6] + [
        _hit(f"https://example.org/new-{n}", rank=7+n) for n in range(4)]))])
    evidence = _run(_runner(gateway), ("first", "second"))
    assert evidence.searched_count == 2
    assert len(evidence.results) == 12
    assert evidence.truncated is True
    assert len(gateway.requests) == 2


def _real_gateway():
    services = ServiceRegistry()
    service = services.register(
        ServiceDefinition(name="research-mcp", version="0.1.0",
                          provider="mcp", category=ServiceCategory.MCP), object(),
    )
    connection = AsyncMock()
    connection.is_connected = True
    connection.list_tools.return_value = SimpleNamespace(tools=[
        SimpleNamespace(name="search", description="Public search", inputSchema={
            "type": "object", "properties": {"query": {"type": "string"}},
            "required": ["query"], "additionalProperties": False,
        }),
    ])
    connection.call_tool.return_value = SimpleNamespace(
        is_error=False, structured_content=_payload(),
    )
    providers = ProviderRegistry(services)
    providers.register(ProviderDefinition(
        provider_id="research.mcp", name="research-mcp",
        version="0.1.0", service_id=service.service_id,
    ), MCPProvider(connection))
    capabilities = CapabilityRegistry(services)
    capabilities.register(CapabilityDefinition(
        capability_id="internet.search", name="Public research", version="1.0.0",
        description="Search via MCP", provider_id="research.mcp",
        provider_type=ProviderType.MCP, category=CapabilityCategory.RESEARCH,
        tool_name="search", risk_level="medium",
    ))
    permissions = PermissionEngine(capabilities)
    return MCPGateway(capabilities, providers, permissions), permissions, connection


def test_real_gateway_permission_engine_default_deny_is_preserved():
    gateway, permissions, connection = _real_gateway()
    with pytest.raises(ResearchAuthorizationError):
        _run(_runner(gateway))
    connection.call_tool.assert_not_awaited()
    assert permissions.audit_records()[0].decision.decision is AuthorizationDecision.DENY


def test_real_registered_gateway_provider_can_be_explicitly_allowed():
    gateway, permissions, connection = _real_gateway()
    permissions.add_policy(PermissionPolicy(
        policy_id="test.owner.research", policy_version="1.0.0",
        principal_id="local_owner", capability_id="internet.search",
        operation_id="internet.search", resource_scope="public-web",
        authorization_level=AuthorizationLevel.READ,
        decision=AuthorizationDecision.ALLOW,
    ))
    result = _run(_runner(gateway))
    assert len(result.results) == 1
    assert result.results[0].provider_id == "research.mcp"
    connection.call_tool.assert_awaited_once_with("search", {"query": "first"})
    assert permissions.audit_records()[-1].decision.decision is AuthorizationDecision.ALLOW
