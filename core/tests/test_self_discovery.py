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
                 "license": {"spdx_id": "MIT"}, "archived": False, "stargazers_count": 128},
                {"full_name": "unlicensed/repo", "license": None},
                {"full_name": "premium/api", "license": {"spdx_id": "Apache-2.0"}, "stargazers_count": 32},
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
    assert result["items"][0]["stars"] == 128
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
                 "license": "MIT", "capability_hint": "MCP", "stars": 128},
                {"repository": "forbidden/paid",
                 "url": "https://github.com/forbidden/paid", "license": "GPL-3.0",
                 "description": "Paid", "capability_hint": "MCP", "stars": 99},
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



def test_full_scan_calls_all_three_gateway_queries_and_never_invents_items(tmp_path):
    gateway = FakeGateway()
    engine = SelfDiscoveryEngine(gateway=gateway, db_path=tmp_path / "full.sqlite3")
    result = _run(engine.run_once(full_scan=True))
    assert [call.arguments["query"] for call in gateway.calls] == list(QUERIES)
    assert result["new_count"] == 1
    assert result["items"][0]["stars"] == 128
    assert result["items"][0]["repository"] == "verified/local"
    assert result["proposal_count"] == 1


def test_old_sqlite_database_migrates_stars_without_erasing_queue(tmp_path):
    import sqlite3
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE evolution_proposals (
            proposal_id TEXT PRIMARY KEY,
            repository TEXT NOT NULL UNIQUE, url TEXT NOT NULL,
            description TEXT NOT NULL, license TEXT NOT NULL,
            capability_hint TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending_owner_review',
            created_at REAL NOT NULL)""")
        db.execute("INSERT INTO evolution_proposals VALUES (?,?,?,?,?,?,?,?)",
                   ("old", "owner/existing", "https://github.com/owner/existing",
                    "Existing", "MIT", "MCP", "pending_owner_review", 1.0))
    engine = SelfDiscoveryEngine(gateway=FakeGateway(), db_path=path)
    assert engine.count() == 1
    assert engine.proposals()[0]["stars"] is None


def test_github_rate_limit_is_not_a_successful_empty_result():
    async def handler(request):
        return httpx.Response(429, json={"message": "API rate limit exceeded"})
    provider = PublicGitHubDiscoveryMCPProvider(
        transport=httpx.MockTransport(handler))
    token = enter_dispatch(DispatchGrant(
        principal_id="local_owner", capability_id=CAPABILITY_ID,
        tool_name="search_open_source", risk_level="low",
        approval_consumed=False,
    ))
    try:
        with pytest.raises(DiscoveryUnavailable, match="rate limit"):
            _run(provider.call_tool("search_open_source", {"query": QUERIES[0]}))
    finally:
        leave_dispatch(token)


def test_http_manual_scan_reports_all_three_queries(tmp_path):
    gateway = FakeGateway()
    engine = SelfDiscoveryEngine(gateway=gateway, db_path=tmp_path / "http.sqlite3")
    app = FastAPI()
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "local_owner"
    app.state.self_discovery = engine
    app.state.storage_mode = "local"
    app.include_router(router)
    response = TestClient(app).post("/api/evolution/discovery/run",
                                    headers={"Authorization": "Bearer " + "t" * 40})
    assert response.status_code == 200, response.text
    assert response.json()["new_count"] == 1
    assert response.json()["items"][0]["stars"] == 128
    assert [call.arguments["query"] for call in gateway.calls] == list(QUERIES)


def test_http_github_rate_limit_surfaces_actual_error(tmp_path):
    class RateLimitedGateway(FakeGateway):
        async def invoke(self, request):
            self.calls.append(request)
            raise DiscoveryUnavailable("GitHub public API rate limit reached (403/429)")
    gateway = RateLimitedGateway()
    engine = SelfDiscoveryEngine(gateway=gateway, db_path=tmp_path / "limited.sqlite3")
    app = FastAPI()
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "local_owner"
    app.state.self_discovery = engine
    app.state.storage_mode = "local"
    app.include_router(router)
    response = TestClient(app).post(
        "/api/evolution/discovery/run",
        headers={"Authorization": "Bearer " + "t" * 40},
    )
    assert response.status_code == 429
    assert "rate limit" in response.json()["detail"]
    assert engine.count() == 0
    assert len(gateway.calls) == 1


def test_discovery_history_is_durable_and_bounded(tmp_path):
    db = tmp_path / "history.sqlite3"
    engine = SelfDiscoveryEngine(gateway=FakeGateway(), db_path=db)
    _run(engine.run_once())
    assert engine.history()[0]["status"] == "COMPLETE"
    restarted = SelfDiscoveryEngine(gateway=FakeGateway(), db_path=db)
    assert restarted.history()[0]["new_proposals"] == 1
    assert restarted.history()[0]["query_count"] == 1


def test_discovery_read_only_history_and_static_inventory(tmp_path):
    from aura_core.evolution.external_staging import EvolutionWorkspace
    gateway = FakeGateway()
    workspace = EvolutionWorkspace(tmp_path / "external")
    engine = SelfDiscoveryEngine(gateway=gateway,
                                 db_path=workspace.root / "catalog" / "proposal.sqlite3",
                                 workspace=workspace)
    _run(engine.run_once())
    app = FastAPI()
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "local_owner"
    app.state.self_discovery = engine
    app.state.storage_mode = "local"
    app.include_router(router)
    client = TestClient(app)
    headers = {"Authorization": "Bearer " + "t" * 40}
    history = client.get("/api/evolution/discovery/history", headers=headers)
    assert history.status_code == 200
    assert history.json()["items"][0]["status"] == "COMPLETE"
    packages = client.get("/api/evolution/discovery/verified", headers=headers)
    assert packages.status_code == 200
    assert packages.json()["activation_performed"] is False
    assert packages.json()["ready_count"] == 0
    assert client.get("/api/evolution/discovery/verified").status_code == 401


def test_auto_staging_calls_second_gateway_tool_but_no_execution(tmp_path):
    from aura_core.evolution.external_staging import EvolutionWorkspace, CAPABILITY
    class StageGateway(FakeGateway):
        async def invoke(self, request):
            if request.capability_id == CAPABILITY:
                self.calls.append(request)
                return SimpleNamespace(decision=AuthorizationDecision.ALLOW, result={
                    "repository": request.arguments["repository"],
                    "status": "READY_FOR_OWNER_REVIEW",
                    "source_sha256": "a" * 64,
                    "sandbox_attested": False,
                    "activation_performed": False,
                })
            return await super().invoke(request)
    workspace = EvolutionWorkspace(tmp_path / "workspace")
    gw = StageGateway()
    engine = SelfDiscoveryEngine(gateway=gw,
                                 db_path=workspace.root / "catalog" / "proposals.sqlite3",
                                 workspace=workspace, auto_stage=True)
    result = _run(engine.run_once())
    assert result["staged_count"] == 1
    assert result["static_ready_count"] == 1
    assert engine.proposals()[0]["package_status"] == "READY_FOR_OWNER_REVIEW"
    assert [call.capability_id for call in gw.calls] == [
        "github.repository.search", "github.repository.stage"
    ]
    assert gw.calls[1].resource_scope == "evolution-staging"
    assert gw.calls[1].risk_level.value == "medium"
    assert workspace.active.exists()
    assert __import__("json").loads(workspace.active.read_text())["active"] == []
    _run(engine.run_once())
    assert [call.capability_id for call in gw.calls].count("github.repository.stage") == 1


def test_denied_staging_never_marks_ready_or_registers_code(tmp_path):
    from aura_core.evolution.external_staging import EvolutionWorkspace, CAPABILITY
    class DeniedStage(FakeGateway):
        async def invoke(self, request):
            if request.capability_id == CAPABILITY:
                self.calls.append(request)
                return SimpleNamespace(decision=AuthorizationDecision.DENY, result=None)
            return await super().invoke(request)
    workspace = EvolutionWorkspace(tmp_path / "workspace")
    engine = SelfDiscoveryEngine(gateway=DeniedStage(),
                                 db_path=workspace.root / "catalog" / "proposals.sqlite3",
                                 workspace=workspace, auto_stage=True)
    result = _run(engine.run_once())
    assert result["staged_count"] == 0
    assert engine.proposals()[0]["package_status"] == "STAGING_REJECTED"
    assert engine.static_ready_count() == 0
    assert workspace.verified_packages() == []
    assert __import__("json").loads(workspace.active.read_text())["active"] == []
