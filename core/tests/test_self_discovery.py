"""Public GitHub discovery: gateway proof, licensing and persistent review queue."""
import asyncio
import base64
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aura_core.evolution.self_discovery import (
    CAPABILITY_ID, QUERIES, PublicGitHubDiscoveryMCPProvider,
    SelfDiscoveryEngine, DiscoveryUnavailable,
)
from aura_core.evolution.self_discovery_api import router
from aura_core.kernel.permissions import AuthorizationDecision
from aura_core.mcp.dispatch_context import DispatchGrant, enter_dispatch, leave_dispatch


def _run(coro):
    return asyncio.run(coro)


def test_public_provider_requires_gateway_dispatch():
    provider = PublicGitHubDiscoveryMCPProvider()
    with pytest.raises(PermissionError):
        _run(provider.call_tool("search_open_source", {"query": QUERIES[0]}))


def test_fixed_origin_and_strict_free_license_filter():
    urls = []
    def handler(request: httpx.Request):
        urls.append(str(request.url))
        assert request.url.host == "api.github.com"
        if request.url.path == "/search/repositories":
            return httpx.Response(200, json={"items": [
                {"full_name": "verified/local", "description": "Local model MCP",
                 "license": {"spdx_id": "MIT"}, "archived": False},
                {"full_name": "unlicensed/repo", "license": None},
                {"full_name": "premium/api", "license": {"spdx_id": "Apache-2.0"}},
            ]})
        if request.url.path.endswith("/verified/local/readme"):
            return httpx.Response(200, json={
                "encoding": "base64",
                "content": base64.b64encode(b"Fully local and offline, no API key required").decode(),
            })
        return httpx.Response(200, json={
            "encoding": "base64",
            "content": base64.b64encode(b"Must set OPENAI_API_KEY for paid service").decode(),
        })

    provider = PublicGitHubDiscoveryMCPProvider(transport=httpx.MockTransport(handler))
    token = enter_dispatch(DispatchGrant(
        principal_id="local_owner", capability_id=CAPABILITY_ID,
        tool_name="search_open_source", approval_consumed=False, risk_level="low",
    ))
    try:
        result = _run(provider.call_tool("search_open_source", {"query": QUERIES[0]}))
    finally:
        leave_dispatch(token)
    assert [item["repository"] for item in result["items"]] == ["verified/local"]
    assert all(url.startswith("https://api.github.com/") for url in urls)


def test_provider_rejects_untrusted_queries_before_network():
    provider = PublicGitHubDiscoveryMCPProvider()
    token = enter_dispatch(DispatchGrant(
        principal_id="local_owner", capability_id=CAPABILITY_ID,
        tool_name="search_open_source", approval_consumed=False, risk_level="low",
    ))
    try:
        with pytest.raises(ValueError, match="Unapproved"):
            _run(provider.call_tool("search_open_source", {"query": "http://127.0.0.1"}))
    finally:
        leave_dispatch(token)


class FakeGateway:
    def __init__(self, decision=AuthorizationDecision.ALLOW):
        self.decision = decision
        self.calls = []

    async def invoke(self, request):
        self.calls.append(request)
        return SimpleNamespace(decision=self.decision, result={
            "items": [
                {"repository": "verified/local",
                 "url": "https://github.com/verified/local", "description": "Offline",
                 "license": "MIT", "capability_hint": "MCP"},
                {"repository": "forbidden/paid",
                 "url": "https://github.com/forbidden/paid", "license": "GPL-3.0",
                 "description": "Paid", "capability_hint": "MCP"},
            ],
        })


def test_persistent_proposals_and_gateway_risk_scope(tmp_path):
    gateway = FakeGateway()
    path = tmp_path / "evolution.sqlite3"
    engine = SelfDiscoveryEngine(gateway=gateway, db_path=path)
    result = _run(engine.run_once())
    assert result["new_count"] == 1
    assert result["activation_performed"] is False
    assert gateway.calls[0].capability_id == CAPABILITY_ID
    assert gateway.calls[0].resource_scope == "public-github"
    assert SelfDiscoveryEngine(gateway=gateway, db_path=path).count() == 1
    assert _run(engine.run_once())["new_count"] == 0


def test_gateway_denial_fails_closed(tmp_path):
    engine = SelfDiscoveryEngine(gateway=FakeGateway(AuthorizationDecision.DENY),
                                 db_path=tmp_path / "denied.sqlite3")
    with pytest.raises(PermissionError, match="MCPGateway denied"):
        _run(engine.run_once())
    assert engine.count() == 0


def test_unauthenticated_or_remote_discovery_fails_closed(tmp_path):
    gateway = FakeGateway()
    engine = SelfDiscoveryEngine(gateway=gateway, db_path=tmp_path / "data.sqlite3")
    app = FastAPI()
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "local_owner"
    app.state.self_discovery = engine
    app.state.storage_mode = "remote"
    app.include_router(router)
    client = TestClient(app)
    assert client.get("/api/evolution/discovery").status_code == 401
    headers = {"Authorization": "Bearer " + "t" * 40}
    assert client.post("/api/evolution/discovery/run", headers=headers).status_code == 503
    assert gateway.calls == []
    app.state.storage_mode = "local"
    r = client.post("/api/evolution/discovery/run", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["proposal_count"] == 1
    assert r.json()["activation_performed"] is False


def test_optional_local_research_requires_a_second_gateway_dispatch(tmp_path, monkeypatch):
    monkeypatch.setenv("AURA_DISCOVERY_USE_RESEARCH_MCP", "1")
    gateway = FakeGateway()
    engine = SelfDiscoveryEngine(gateway=gateway, db_path=tmp_path / "research.sqlite3")
    result = _run(engine.run_once())
    assert result["local_research_crosscheck"] == "gateway_queried"
    assert [call.capability_id for call in gateway.calls] == [
        "github.repository.search", "internet.search"
    ]
    assert result["items"][0]["integration_blueprint"]["entrypoint"] is None
    assert result["activation_performed"] is False
