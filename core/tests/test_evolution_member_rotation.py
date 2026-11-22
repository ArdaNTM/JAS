"""Regression: bounded 1500-member GitHub ZIPs and durable novelty-first search rotation."""
from __future__ import annotations

import asyncio
import io
import json
import sqlite3
import stat
import zipfile
from types import SimpleNamespace

import pytest

from aura_core.evolution.external_staging import (
    _archive_member_budget, _validated_files, EvolutionWorkspace,
    GitHubStagingMCPProvider, StagingRejected,
    CAPABILITY as STAGE_CAPABILITY, TOOL as STAGE_TOOL,
)
from aura_core.evolution.self_discovery import (
    CAPABILITY_ID, QUERIES, SelfDiscoveryEngine,
)
from aura_core.kernel.permissions import AuthorizationDecision
from aura_core.mcp.dispatch_context import DispatchGrant, enter_dispatch, leave_dispatch
import httpx


def _archive(asset_count=0, *, directories=0, payload=b"\x89PNG\x00"):
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("local-repo/README.md", "Fully local, offline MCP tool, no API key required")
        bundle.writestr("local-repo/server.py", "from fastmcp import FastMCP\napp = FastMCP('test')\n")
        for i in range(directories):
            bundle.writestr(f"local-repo/directory-{i:04d}/", b"")
        for i in range(asset_count):
            bundle.writestr(f"local-repo/assets/icon-{i:04d}.png", payload)
    return memory.getvalue()


def test_archive_member_budget_default_1500_and_override(monkeypatch):
    monkeypatch.delenv("AURA_EVOLUTION_MAX_ARCHIVE_MEMBERS", raising=False)
    assert _archive_member_budget() == 1500
    files, entrypoint, skipped = _validated_files(_archive(1498))
    assert len(files) == 2
    assert entrypoint == "server.py"
    assert skipped == 1498
    with pytest.raises(StagingRejected, match="too many members"):
        _validated_files(_archive(1499))
    # Directories count toward the same total, including those with no files.
    with pytest.raises(StagingRejected, match="too many members"):
        _validated_files(_archive(0, directories=1499))

    monkeypatch.setenv("AURA_EVOLUTION_MAX_ARCHIVE_MEMBERS", "4")
    files, _, skipped = _validated_files(_archive(2))
    assert len(files) == 2 and skipped == 2
    with pytest.raises(StagingRejected, match="too many members"):
        _validated_files(_archive(3))
    monkeypatch.setenv("AURA_EVOLUTION_MAX_ARCHIVE_MEMBERS", "1600")
    assert _archive_member_budget() == 1600


@pytest.mark.parametrize("bad", ["", "-1", "0", "abc", "1.5", "999999", " "])
def test_invalid_archive_member_budget_fails_closed(monkeypatch, bad):
    monkeypatch.setenv("AURA_EVOLUTION_MAX_ARCHIVE_MEMBERS", bad)
    with pytest.raises(StagingRejected, match="member budget"):
        _archive_member_budget()


def test_large_member_budget_does_not_bypass_security_limits(monkeypatch):
    monkeypatch.setenv("AURA_EVOLUTION_MAX_ARCHIVE_MEMBERS", "1500")
    # A symlink gets rejected even if under the new member budget.
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w") as bundle:
        bundle.writestr("root/README.md", "offline, no api key")
        bundle.writestr("root/server.py", "from fastmcp import FastMCP")
        info = zipfile.ZipInfo("root/assets/symlink.png")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        bundle.writestr(info, "escape")
    with pytest.raises(StagingRejected, match="symlink|special"):
        _validated_files(memory.getvalue())

    with pytest.raises(StagingRejected, match="Executable"):
        _validated_files(_archive(1, payload=b"x") + b"\x00" * (32 * 1024 * 1024 + 1))
    # Actual executable ZIP member is blocked, not skipped.
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("root/README.md", "Fully local offline MCP")
        bundle.writestr("root/server.py", "from fastmcp import FastMCP")
        bundle.writestr("root/assets/evil.dll", b"\x00 executable")
    with pytest.raises(StagingRejected, match="Executable"):
        _validated_files(memory.getvalue())
    with pytest.raises(StagingRejected, match="maximum byte budget"):
        _validated_files(b"x" * (32 * 1024 * 1024 + 1))


def test_live_legacy_archive_rejection_is_retried_and_verified(tmp_path):
    workspace = EvolutionWorkspace(tmp_path / "outside")
    repo = "Cranot/roam-code"
    archive = _archive(130)
    sha = "d" * 40
    def handler(request):
        if request.url.path == "/repos/" + repo:
            return httpx.Response(200, json={
                "full_name": repo, "private": False, "fork": False,
                "archived": False, "license": {"spdx_id": "Apache-2.0"},
                "description": "Local offline sqlite MCP server, zero API keys",
            })
        if request.url.path == "/repos/" + repo + "/commits":
            return httpx.Response(200, json=[{"sha": sha}])
        if request.url.host == "codeload.github.com":
            return httpx.Response(200, content=archive)
        raise AssertionError("Unexpected URL " + str(request.url))
    provider = GitHubStagingMCPProvider(workspace=workspace, transport=httpx.MockTransport(handler))
    calls = []
    class Gateway:
        async def invoke(self, request):
            calls.append(request)
            if request.capability_id == CAPABILITY_ID:
                return SimpleNamespace(decision=AuthorizationDecision.ALLOW, result={"items": []})
            assert request.capability_id == STAGE_CAPABILITY
            token = enter_dispatch(DispatchGrant(
                principal_id="local_owner", capability_id=STAGE_CAPABILITY,
                tool_name=STAGE_TOOL, risk_level="medium", approval_consumed=False,
            ))
            try:
                result = await provider.call_tool(STAGE_TOOL, request.arguments)
            finally:
                leave_dispatch(token)
            return SimpleNamespace(decision=AuthorizationDecision.ALLOW, result=result)
    engine = SelfDiscoveryEngine(
        gateway=Gateway(), db_path=workspace.root / "catalog" / "proposals.sqlite3",
        workspace=workspace, auto_stage=True,
    )
    with sqlite3.connect(engine._db_path) as db:
        db.execute(
            "INSERT INTO evolution_proposals "
            "(proposal_id,repository,url,description,license,capability_hint,created_at,"
            "stars,size_kb,package_status,package_error,stage_attempts) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("cranot", repo, "https://github.com/" + repo,
             "Local sqlite filesystem MCP, zero API keys", "Apache-2.0",
             "MCP", 1.0, 150, 800, "STAGING_REJECTED", "Archive has too many members", 1),
        )
    result = asyncio.run(engine.run_once())
    assert result["new_count"] == 0
    assert result["staging_attempted"] == result["verified_count"] == 1
    assert result["activation_performed"] is False
    assert (workspace.root / "staging" / "Cranot__roam-code" / "source" / "server.py").is_file()
    assert (workspace.root / "verified" / "Cranot__roam-code" / "source.zip").is_file()
    assert engine.proposals()[0]["package_status"] == "READY_FOR_OWNER_REVIEW"
    assert json.loads(workspace.active.read_text())["active"] == []


def test_rotates_eight_fixed_queries_two_per_manual_scan_across_restarts(tmp_path):
    assert len(QUERIES) >= 8 and len(set(QUERIES)) == len(QUERIES)
    path = tmp_path / "persistent.sqlite3"
    observed = []
    class Gateway:
        async def invoke(self, request):
            assert request.capability_id == CAPABILITY_ID
            observed.append(request.arguments["query"])
            return SimpleNamespace(decision=AuthorizationDecision.ALLOW, result={"items": []})
    engine = SelfDiscoveryEngine(gateway=Gateway(), db_path=path)
    for round_index in range(2):
        result = asyncio.run(engine.run_once(full_scan=True))
        assert result["successful_queries"] == 2
        assert result["new_count"] == 0
        assert observed[2*round_index:2*round_index+2] == list(
            QUERIES[2*round_index:2*round_index+2]
        )
    # Rotation must survive process restarts as Windows starts a fresh daemon.
    restarted = SelfDiscoveryEngine(gateway=Gateway(), db_path=path)
    asyncio.run(restarted.run_once(full_scan=True))
    assert observed[4:6] == list(QUERIES[4:6])
    asyncio.run(restarted.run_once(full_scan=True))
    assert observed[6:8] == list(QUERIES[6:8])
    asyncio.run(restarted.run_once(full_scan=True))
    assert observed[8:10] == list(QUERIES[0:2])


def test_novel_results_precede_previously_catalogued_search_results(tmp_path):
    db_path = tmp_path / "prior.sqlite3"
    calls = []
    class Gateway:
        async def invoke(self, request):
            calls.append(request)
            assert request.arguments["query"] in QUERIES
            return SimpleNamespace(decision=AuthorizationDecision.ALLOW, result={"items": [
                {"repository": f"local/repo-{i}", "url": f"https://github.com/local/repo-{i}",
                 "description": "Fully local fastmcp sqlite", "license": "MIT",
                 "capability_hint": "MCP", "stars": 1000-i, "size_kb": 80}
                for i in range(6)
            ]})
    engine = SelfDiscoveryEngine(gateway=Gateway(), db_path=db_path)
    # Seed the three most popular results, so the new candidates should win.
    with sqlite3.connect(db_path) as db:
        for i in range(3):
            db.execute(
                "INSERT INTO evolution_proposals "
                "(proposal_id,repository,url,description,license,capability_hint,created_at,stars) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (str(i), f"local/repo-{i}", f"https://github.com/local/repo-{i}",
                 "Fully local fastmcp sqlite", "MIT", "MCP", float(i), 1000-i),
            )
    result = asyncio.run(engine.run_once())
    assert result["new_count"] == 3
    assert engine.count() == 6
    assert all(x["repository"] in {f"local/repo-{i}" for i in range(3, 6)}
               for x in result["items"] if x["repository"] not in {f"local/repo-{i}" for i in range(3)})
    assert result["activation_performed"] is False
