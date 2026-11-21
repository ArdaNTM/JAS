"""Live Windows evolution regressions: bounded GitHub recovery and read-only Owner UI."""
from __future__ import annotations

import asyncio
import io
import json
import sqlite3
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from aura_core.evolution.external_staging import (
    CAPABILITY as STAGE_CAPABILITY, TOOL as STAGE_TOOL,
    EvolutionWorkspace, GitHubStagingMCPProvider, StagingRejected,
)
from aura_core.evolution.self_discovery import (
    CAPABILITY_ID, QUERIES, DiscoveryUnavailable, PublicGitHubDiscoveryMCPProvider,
    SelfDiscoveryEngine,
)
from aura_core.kernel.permissions import AuthorizationDecision
from aura_core.mcp.dispatch_context import DispatchGrant, enter_dispatch, leave_dispatch


def archive():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("repo-abc/README.md", "Fully local and offline MCP tool")
        bundle.writestr("repo-abc/server.py", "from fastmcp import FastMCP\napp = FastMCP('test')\n")
    return output.getvalue()


def run_stage(provider, repository="sample/worker"):
    async def call():
        grant = enter_dispatch(DispatchGrant(
            principal_id="local_owner", capability_id=STAGE_CAPABILITY,
            tool_name=STAGE_TOOL, risk_level="medium", approval_consumed=False,
        ))
        try:
            return await provider.call_tool(STAGE_TOOL, {"repository": repository})
        finally:
            leave_dispatch(grant)
    return asyncio.run(call())


def test_302_archive_redirect_to_codeload_is_bounded_and_static(tmp_path):
    visited = []
    sha = "a" * 40

    def handler(request):
        visited.append(str(request.url))
        if request.url.path == "/repos/sample/worker":
            return httpx.Response(200, json={
                "full_name": "sample/worker", "private": False, "fork": False,
                "archived": False, "license": {"spdx_id": "MIT"},
                "description": "Fully local offline MCP",
            })
        if request.url.path == "/repos/sample/worker/commits":
            return httpx.Response(200, json=[{"sha": sha}])
        if request.url.path == "/sample/worker/zip/" + sha:
            return httpx.Response(302, headers={
                "Location": "https://codeload.github.com/sample/worker/legacy.zip",
            })
        if request.url.path == "/sample/worker/legacy.zip":
            return httpx.Response(200, content=archive())
        raise AssertionError("Unexpected outbound request " + str(request.url))

    workspace = EvolutionWorkspace(tmp_path / "external")
    result = run_stage(GitHubStagingMCPProvider(
        workspace=workspace, transport=httpx.MockTransport(handler),
    ))
    assert result["status"] == "READY_FOR_OWNER_REVIEW"
    assert result["owner_approved"] is False
    assert result["execution_allowed"] is False
    assert (workspace.root / "staging" / "sample__worker" / "source" / "server.py").exists()
    assert (workspace.root / "verified" / "sample__worker" / "source.zip").exists()
    assert all(url.startswith(("https://api.github.com/", "https://codeload.github.com/"))
               for url in visited)


@pytest.mark.parametrize("location", [
    "http://codeload.github.com/unsafe",
    "https://evil.example/archive.zip",
    "https://localhost/archive.zip",
    "https://api.github.com.evil.example/archive",
    "https://user:secret@codeload.github.com/archive",
    "https://codeload.github.com:444/archive.zip",
])
def test_redirect_other_origins_fail_closed(tmp_path, location):
    sha = "a" * 40
    def handler(request):
        if request.url.path == "/repos/sample/worker":
            return httpx.Response(200, json={
                "full_name": "sample/worker", "private": False, "fork": False,
                "archived": False, "license": {"spdx_id": "MIT"},
            })
        if request.url.path == "/repos/sample/worker/commits":
            return httpx.Response(200, json=[{"sha": sha}])
        return httpx.Response(302, headers={"Location": location})
    workspace = EvolutionWorkspace(tmp_path / "external")
    with pytest.raises(StagingRejected, match="redirect|host|origin"):
        run_stage(GitHubStagingMCPProvider(
            workspace=workspace, transport=httpx.MockTransport(handler),
        ))
    assert workspace.verified_packages() == []


def test_github_bearer_used_only_when_provisioned(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_example_token_123456789")
    observed = []
    def handler(request):
        observed.append(request)
        return httpx.Response(200, json={"items": []})
    provider = PublicGitHubDiscoveryMCPProvider(transport=httpx.MockTransport(handler))
    async def exercise():
        async with httpx.AsyncClient(transport=provider._transport) as client:
            return await provider._get(client, "/search/repositories")
    assert asyncio.run(exercise()) == {"items": []}
    assert observed[0].headers["Authorization"] == "Bearer ghp_example_token_123456789"


def test_public_scan_uses_at_most_two_queries_and_six_results(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("PATH", "")
    assert 1 <= len(QUERIES) <= 2
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"items": []})
    provider = PublicGitHubDiscoveryMCPProvider(transport=httpx.MockTransport(handler))
    async def exercise():
        grant = enter_dispatch(DispatchGrant(
            principal_id="local_owner", capability_id=CAPABILITY_ID,
            tool_name="search_open_source", risk_level="low", approval_consumed=False,
        ))
        try:
            return await provider.call_tool("search_open_source", {"query": QUERIES[0]})
        finally:
            leave_dispatch(grant)
    asyncio.run(exercise())
    assert requests[0].url.params["per_page"] == "6"
    assert "Authorization" not in requests[0].headers


@pytest.mark.parametrize("status", [403, 429])
def test_rate_limited_search_stages_existing_catalog_without_approval(tmp_path, status):
    from aura_core.evolution.external_staging import staging_scope
    workspace = EvolutionWorkspace(tmp_path / "external")
    sha = "a" * 40
    calls = []
    def handler(request):
        segments = request.url.path.strip("/").split("/")
        if len(segments) >= 3 and segments[0] == "repos":
            repo = "/".join(segments[1:3])
            if len(segments) == 3:
                return httpx.Response(200, json={
                    "full_name": repo, "private": False, "fork": False,
                    "archived": False, "license": {"spdx_id": "MIT"},
                    "description": "Fully local offline MCP",
                })
            if segments[-1] == "commits":
                return httpx.Response(200, json=[{"sha": sha}])
        if request.url.host == "codeload.github.com":
            return httpx.Response(200, content=archive())
        raise AssertionError("Unexpected request " + str(request.url))
    staging = GitHubStagingMCPProvider(workspace=workspace, transport=httpx.MockTransport(handler))

    class Gateway:
        async def invoke(self, request):
            calls.append(request)
            if request.capability_id == CAPABILITY_ID:
                raise DiscoveryUnavailable(f"GitHub public API rate limit reached ({status})")
            assert request.capability_id == STAGE_CAPABILITY
            assert request.resource_scope == staging_scope(workspace)
            grant = enter_dispatch(DispatchGrant(
                principal_id="local_owner", capability_id=STAGE_CAPABILITY,
                tool_name=STAGE_TOOL, risk_level="medium", approval_consumed=False,
            ))
            try:
                proof = await staging.call_tool(STAGE_TOOL, request.arguments)
            finally:
                leave_dispatch(grant)
            return SimpleNamespace(decision=AuthorizationDecision.ALLOW, result=proof)

    engine = SelfDiscoveryEngine(
        gateway=Gateway(), db_path=workspace.root / "catalog" / "proposals.sqlite3",
        workspace=workspace, auto_stage=True,
    )
    with sqlite3.connect(engine._db_path) as db:
        for i in range(4):
            repo = f"sample/worker-{i}"
            db.execute(
                "INSERT INTO evolution_proposals "
                "(proposal_id,repository,url,description,license,capability_hint,created_at,stars)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (f"p{i}", repo, "https://github.com/" + repo, "Offline fastmcp",
                 "MIT", "MCP", float(i), 100),
            )
    result = asyncio.run(engine.run_once(full_scan=True))
    assert result["partial"] is True
    assert result["successful_queries"] == 0
    assert result["staging_attempted"] == 3
    assert result["staged_count"] == result["verified_count"] == 3
    assert len([call for call in calls if call.capability_id == STAGE_CAPABILITY]) == 3
    assert len(list((workspace.root / "verified").iterdir())) == 3
    assert len(list((workspace.root / "staging").iterdir())) == 3
    assert json.loads(workspace.active.read_text())["active"] == []


def test_local_owner_review_starts_on_loopback_and_lists_catalog(tmp_path, monkeypatch):
    from aura_core.evolution.owner_control_plane_http import build_local_review_app, main
    workspace = EvolutionWorkspace(tmp_path / "external")
    engine = SelfDiscoveryEngine(
        gateway=None, db_path=workspace.root / "catalog" / "proposals.sqlite3",
    )
    with sqlite3.connect(engine._db_path) as db:
        db.execute(
            "INSERT INTO evolution_proposals "
            "(proposal_id,repository,url,description,license,capability_hint,created_at,stars)"
            " VALUES (?,?,?,?,?,?,?,?)",
            ("p1", "sample/worker", "https://github.com/sample/worker",
             "Local MCP utility", "MIT", "MCP", 1.0, 20),
        )
    app = build_local_review_app(workspace.root)
    with TestClient(app, base_url="http://localhost:8766") as client:
        response = client.get("/api/owner/discoveries")
        assert response.status_code == 200
        assert response.json()["items"][0]["repository"] == "sample/worker"
        assert client.get("/").status_code == 200
        assert client.get("/api/owner/discoveries",
                          headers={"Host": "evil.example"}).status_code == 403
        assert client.post("/api/owner/challenge", json={"approval_id": "x"},
                           headers={"Origin": "http://localhost:8766"}).status_code == 503
        assert client.post("/api/owner/challenge", json={"approval_id": "x"},
                           headers={"Origin": "http://127.0.0.1:4173"}).status_code == 403
        assert client.get("/api/owner/health").json()["activation_allowed"] is False
    captured = {}
    def fake_run(app, **kwargs):
        captured.update(kwargs)
    monkeypatch.setattr("uvicorn.run", fake_run)
    monkeypatch.setattr(sys, "argv", ["owner_control_plane_http", "--evolution-root", str(workspace.root)])
    main()
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8766
    assert captured["workers"] == 1
