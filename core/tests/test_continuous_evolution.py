"""Continuous Evolution: fixed-origin discovery, Owner gating, pause and safe status."""
import asyncio
import base64
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aura_core.evolution.self_discovery import (
    CATALOG_CAPABILITY, CATALOG_TOOL, PublicCatalogDiscoveryMCPProvider,
    SelfDiscoveryEngine, QUERIES,
)
from aura_core.evolution.continuous_evolution import ContinuousEvolutionController
from aura_core.evolution.self_discovery_api import continuous_router
from aura_core.mcp.dispatch_context import DispatchGrant, enter_dispatch, leave_dispatch
from aura_core.security.http_auth import authenticated_principal
from aura_core.kernel.permissions import AuthorizationDecision


def run(coro):
    return asyncio.run(coro)


def _catalog_handler(request: httpx.Request) -> httpx.Response:
    assert request.url.host in {"api.github.com", "pypi.org", "registry.modelcontextprotocol.io"}
    assert request.method == "GET"
    if request.url.host == "registry.modelcontextprotocol.io":
        return httpx.Response(200, json={"servers": [
            {"server": {"name": "io.github.demo/memory", "description": "Local memory",
                        "repository": {"url": "https://github.com/demo/memory"}}},
            {"server": {"name": "malicious", "repository": {"url": "http://localhost/bad"}}},
        ]})
    if request.url.host == "pypi.org":
        return httpx.Response(200, json={"info": {
            "name": "mcp-server-memory", "summary": "Local memory MCP",
            "keywords": "mcp fastmcp",
            "project_urls": {"Source": "https://github.com/demo/memory"},
        }})
    if request.url.path == "/repos/demo/memory":
        return httpx.Response(200, json={
            "full_name": "demo/memory", "private": False, "archived": False,
            "fork": False, "stargazers_count": 12, "size": 50,
            "license": {"spdx_id": "MIT"}, "language": "Python",
            "description": "Local offline memory MCP",
        })
    if request.url.path == "/repos/demo/memory/readme":
        return httpx.Response(200, json={
            "encoding": "base64", "content": base64.b64encode(
                b"Fully local offline Python FastMCP server no API key required"
            ).decode(),
        })
    return httpx.Response(404)


@pytest.mark.parametrize("source", ["registry", "pypi"])
def test_catalog_sources_must_be_gateway_authorized_and_github_verified(source):
    provider = PublicCatalogDiscoveryMCPProvider(transport=httpx.MockTransport(_catalog_handler))
    args = {"source": source}
    with pytest.raises(PermissionError):
        run(provider.call_tool(CATALOG_TOOL, args))
    token = enter_dispatch(DispatchGrant(
        principal_id="local_owner", capability_id=CATALOG_CAPABILITY,
        tool_name=CATALOG_TOOL, approval_consumed=False, risk_level="low",
    ))
    try:
        result = run(provider.call_tool(CATALOG_TOOL, args))
    finally:
        leave_dispatch(token)
    assert [entry["repository"] for entry in result["items"]] == ["demo/memory"]
    assert result["items"][0]["license"] == "MIT"
    assert result["items"][0]["url"] == "https://github.com/demo/memory"


def test_catalog_denies_nonallowlisted_source_and_redirect():
    def redirected(req):
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})
    provider = PublicCatalogDiscoveryMCPProvider(transport=httpx.MockTransport(redirected))
    token = enter_dispatch(DispatchGrant(
        principal_id="local_owner", capability_id=CATALOG_CAPABILITY,
        tool_name=CATALOG_TOOL, approval_consumed=False, risk_level="low",
    ))
    try:
        with pytest.raises(ValueError):
            run(provider.call_tool(CATALOG_TOOL, {"source": "http://localhost"}))
        with pytest.raises(RuntimeError):
            run(provider.call_tool(CATALOG_TOOL, {"source": "registry"}))
    finally:
        leave_dispatch(token)


def test_catalog_rate_limit_is_explicit_and_bounded():
    provider = PublicCatalogDiscoveryMCPProvider(transport=httpx.MockTransport(
        lambda _: httpx.Response(429, headers={"Retry-After": "30"}),
    ))
    token = enter_dispatch(DispatchGrant(
        principal_id="local_owner", capability_id=CATALOG_CAPABILITY,
        tool_name=CATALOG_TOOL, approval_consumed=False, risk_level="low",
    ))
    try:
        with pytest.raises(RuntimeError, match="rate limit"):
            run(provider.call_tool(CATALOG_TOOL, {"source": "pypi"}))
    finally:
        leave_dispatch(token)


class Gateway:
    def __init__(self):
        self.calls = []

    async def invoke(self, request):
        self.calls.append(request)
        if request.capability_id == CATALOG_CAPABILITY:
            return SimpleNamespace(decision=AuthorizationDecision.ALLOW, result={
                "items": [{"repository": "demo/memory",
                           "url": "https://github.com/demo/memory",
                           "description": "Offline memory",
                           "license": "MIT", "capability_hint": "FastMCP",
                           "stars": 12, "size_kb": 50}],
            })
        return SimpleNamespace(decision=AuthorizationDecision.ALLOW, result={"items": []})


def test_multisource_persistent_catalog_and_dedup(tmp_path):
    gateway = Gateway()
    engine = SelfDiscoveryEngine(gateway=gateway, db_path=tmp_path / "catalog.sqlite3")
    first = run(engine.run_once(multi_source=True))
    assert first["new_count"] == 1
    assert engine.count() == 1
    assert sum(c.capability_id == CATALOG_CAPABILITY for c in gateway.calls) == 2
    assert all(c.arguments.get("source") in {"registry", "pypi"} for c in gateway.calls
               if c.capability_id == CATALOG_CAPABILITY)
    again = run(engine.run_once(multi_source=True))
    assert again["new_count"] == 0
    assert engine.count() == 1
    assert all(c.capability_id.startswith(("public.mcp", "github.")) for c in gateway.calls)


class FakeDiscovery:
    def __init__(self):
        self.calls = 0
        self.workspace = None
        self._last_error = ""

    async def run_once(self, **kwargs):
        self.calls += 1
        return {"new_count": 2, "staged_count": 0, "proposal_count": 2,
                "failed_queries": [], "auto_activated": []}

    def status(self):
        return {"proposal_count": 2, "verified_static_count": 0, "last_error": ""}


class FakeManager:
    def __init__(self):
        self.scans = 0

    async def scan(self):
        self.scans += 1
        return []

    def active_summary(self):
        return []


def test_controller_start_stop_idempotent_bounded_cycle():
    async def scenario():
        discovery, manager = FakeDiscovery(), FakeManager()
        controller = ContinuousEvolutionController(
            discovery=discovery, activation=manager, interval_seconds=180,
        )
        assert controller.status()["state"] == "IDLE"
        assert controller.start()["state"] == "RUNNING"
        assert controller.start()["state"] == "RUNNING"
        await asyncio.sleep(0.02)
        assert discovery.calls == 1
        assert manager.scans == 1
        assert controller.status()["scanned_candidates"] == 2
        assert controller.status()["active_count"] == 0
        assert (await controller.stop())["state"] == "IDLE"
        assert (await controller.stop())["state"] == "IDLE"
    run(scenario())


def test_continuous_routes_require_local_owner_and_do_not_issue_signatures():
    discovery, manager = FakeDiscovery(), FakeManager()
    app = FastAPI()
    app.state.storage_mode = "local"
    app.state.self_discovery = discovery
    app.state.continuous_evolution = ContinuousEvolutionController(
        discovery=discovery, activation=manager,
    )
    app.include_router(continuous_router)
    app.dependency_overrides[authenticated_principal] = lambda: "other_principal"
    with TestClient(app) as client:
        assert client.get("/api/evolution/continuous/status").status_code == 403
        assert client.post("/api/evolution/continuous/start").status_code == 403
    app.dependency_overrides[authenticated_principal] = lambda: "local_owner"
    with TestClient(app) as client:
        assert client.get("/api/evolution/continuous/status").json()["state"] == "IDLE"
        assert client.post("/api/evolution/continuous/start").json()["state"] == "RUNNING"
        assert client.post("/api/evolution/continuous/stop").json()["state"] == "IDLE"
        assert manager.scans <= 1
