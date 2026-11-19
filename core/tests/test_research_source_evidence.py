"""Research provenance must never turn untrusted results into authority."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.research.evidence import collect_search_evidence
from aura_core.research.mcp_source import MCPResearchSource


def test_canonicalization_deduplication_and_hashes_are_deterministic():
    sources = [
        {"title": "Title", "url": "HTTPS://Example.ORG:443/path?q=1#fragment",
         "snippet": "untrusted body"},
        {"title": "Duplicate", "url": "https://example.org/path?q=1", "snippet": "other"},
        {"title": "Other", "url": "http://other.example/article", "snippet": "quote"},
    ]
    result = collect_search_evidence({"results": sources})
    assert len(result) == 2
    assert result[0]["url"] == "https://example.org/path?q=1"
    assert result[0]["host"] == "example.org"
    assert len(result[0]["source_ref"]) == 64
    assert len(result[0]["snippet_sha256"]) == 64
    assert result == collect_search_evidence({"results": sources})
    assert all(x["untrusted"] and not x["page_retrieved"]
               and not x["source_verified"] for x in result)


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.org/a", "https://localhost/",
    "http://127.0.0.1:8000/", "http://10.1.2.3/",
    "http://192.168.1.4/", "http://169.254.169.254/",
    "https://user:secret@example.org/", "http://intranet.local/",
    "https://example.org:bad/", "https://singlelabel/", "https://example.org/a b",
])
def test_invalid_or_local_literal_source_urls_are_not_promoted(url):
    assert collect_search_evidence({"results": [{"url": url}]}) == ()


def test_bad_shape_and_huge_source_list_are_bounded():
    large = [{"url": f"https://example.org/{i}", "title": "title" * 100}
             for i in range(300)]
    assert len(collect_search_evidence({"results": large}, limit=25)) == 25
    assert collect_search_evidence({"results": "not a list"}) == ()
    assert collect_search_evidence(SimpleNamespace(
        isError=True, structuredContent={"results": large}
    )) == ()
    assert collect_search_evidence(SimpleNamespace(
        isError=False, structuredContent={"results": large}
    ), limit=5) == collect_search_evidence({"results": large}, limit=5)


@pytest.mark.parametrize("bad", [0, 26, True, -1, "10"])
def test_bad_limit_rejected(bad):
    with pytest.raises(ValueError):
        collect_search_evidence({"results": []}, limit=bad)


class SpyGateway:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def invoke(self, request):
        self.calls.append(request)
        return self.response


def _source(gateway):
    spec = SimpleNamespace(
        search_capability_id="internet.search",
        search_operation_id="internet.search",
        search_tool_name="search",
    )
    return MCPResearchSource(gateway, spec)


def test_authorized_gateway_result_produces_untrusted_evidence():
    gateway = SpyGateway(SimpleNamespace(
        decision=AuthorizationDecision.ALLOW,
        result={"results": [{"url": "https://example.org/", "snippet": "hi"}]},
    ))
    response, evidence = asyncio.run(_source(gateway).search_with_evidence(
        principal_id="owner", query="research", resource_scope="public-web",
        risk_level=RiskLevel.LOW, task_id="task-1",
    ))
    assert response.decision is AuthorizationDecision.ALLOW
    assert len(evidence) == 1
    assert evidence[0]["source_verified"] is False
    assert len(gateway.calls) == 1
    assert gateway.calls[0].resource_scope == "public-web"
    assert gateway.calls[0].principal_id == "owner"


def test_denied_gateway_result_never_exposes_provenance():
    gateway = SpyGateway(SimpleNamespace(
        decision=AuthorizationDecision.DENY,
        result={"results": [{"url": "https://private.example.org/"}]},
    ))
    response, evidence = asyncio.run(_source(gateway).search_with_evidence(
        principal_id="other", query="secret", resource_scope="private-files",
        risk_level=RiskLevel.LOW, task_id="task-2",
    ))
    assert response.decision is AuthorizationDecision.DENY
    assert evidence == ()
