"""TDD: resilient bounded static staging for local-first GitHub discoveries."""
from __future__ import annotations

import asyncio
import io
import json
import os
import sqlite3
import stat
import zipfile
from types import SimpleNamespace

import httpx
import pytest

from aura_core.evolution.external_staging import (
    CAPABILITY as STAGE_CAPABILITY, EvolutionWorkspace, GitHubStagingMCPProvider,
    StagingRejected, _archive_budget, _validated_files,
)
from aura_core.evolution.self_discovery import (
    CAPABILITY_ID, SelfDiscoveryEngine, _local_rank,
)
from aura_core.kernel.permissions import AuthorizationDecision


def _zip(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
        for path, content in files.items():
            z.writestr("project-root/" + path, content)
    return stream.getvalue()


def _source(**assets):
    return _zip({
        "README.md": b"Fully local and offline MCP server, zero API keys.",
        "server.py": b"from fastmcp import FastMCP\napp = FastMCP('local')\n",
        **assets,
    })


def test_download_budget_defaults_to_exact_32_mib_and_is_configurable(monkeypatch, tmp_path):
    monkeypatch.delenv("AURA_EVOLUTION_MAX_DOWNLOAD_BYTES", raising=False)
    assert _archive_budget() == 33_554_432
    provider = GitHubStagingMCPProvider(
        workspace=EvolutionWorkspace(tmp_path / "external"),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 3_200_001)),
    )

    async def read(limit):
        async with httpx.AsyncClient(transport=provider._transport) as client:
            return await provider._read(client, "https://codeload.github.com/x/y/zip/abc",
                                        max_bytes=limit)

    assert len(asyncio.run(read(_archive_budget()))) == 3_200_001
    monkeypatch.setenv("AURA_EVOLUTION_MAX_DOWNLOAD_BYTES", "4194304")
    assert _archive_budget() == 4_194_304
    monkeypatch.setenv("AURA_EVOLUTION_MAX_DOWNLOAD_BYTES", "2097152")
    with pytest.raises(StagingRejected, match="download byte budget exceeded"):
        asyncio.run(read(_archive_budget()))


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "99999999999999999", " "])
def test_invalid_download_budget_fails_closed(monkeypatch, value):
    monkeypatch.setenv("AURA_EVOLUTION_MAX_DOWNLOAD_BYTES", value)
    with pytest.raises(StagingRejected, match="download budget"):
        _archive_budget()


def test_benign_binary_assets_skipped_while_text_sources_still_scanned(tmp_path):
    archive = _source(**{
        "assets/logo.png": b"\x89PNG\r\n\x1a\n\x00" + b"x" * 30,
        "assets/favicon.ico": b"\x00\x00\x01\x00" + b"x" * 40,
        "assets/font.woff2": b"wOF2\x00" + b"x" * 40,
    })
    files, entrypoint, skipped = _validated_files(archive)
    assert sorted(files) == ["README.md", "server.py"]
    assert entrypoint == "server.py"
    assert skipped == 3
    assert not any(p.startswith("assets/") for p in files)


@pytest.mark.parametrize("name", [
    "malware.exe", "evil.dll", "native.so", "malware.jar", "code.wasm",
    "extension.node", "script.ps1", "installer.msi", "bytecode.pyc",
])
def test_executable_artifacts_rejected_even_with_valid_source(name):
    with pytest.raises(StagingRejected, match="Executable|suspicious"):
        _validated_files(_source(**{"assets/" + name: b"\x00 malicious payload"}))


def test_unknown_binary_rejected_and_zip_symlink_denied():
    with pytest.raises(StagingRejected, match="Binary"):
        _validated_files(_source(**{"assets/opaque.dat": b"\x00\x01\x02"}))
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr("root/README.md", "Fully local and offline")
        z.writestr("root/server.py", "from fastmcp import FastMCP")
        link = zipfile.ZipInfo("root/assets/icon.png")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(link, "target")
    with pytest.raises(StagingRejected, match="symlink|special"):
        _validated_files(stream.getvalue())


def test_large_binary_cannot_bypass_per_file_and_member_count_budgets():
    with pytest.raises(StagingRejected, match="file budget"):
        _validated_files(_source(**{"assets/big.png": os.urandom(750_001)}))
    assets = {f"assets/icon-{i}.png": b"\x89PNG\x00" for i in range(125)}
    with pytest.raises(StagingRejected, match="too many|file budget"):
        _validated_files(_source(**assets))


def test_staged_manifest_audits_skips_but_never_executes(tmp_path):
    from aura_core.evolution.external_staging import TOOL
    from aura_core.mcp.dispatch_context import DispatchGrant, enter_dispatch, leave_dispatch
    sha = "a" * 40
    archive = _source(**{"images/picture.png": b"\x89PNG\x00", "fonts/main.woff": b"wOFF\x00"})
    def handler(request):
        if request.url.path == "/repos/local/demo":
            return httpx.Response(200, json={
                "full_name": "local/demo", "private": False, "fork": False,
                "archived": False, "license": {"spdx_id": "MIT"},
                "description": "Fully local offline",
            })
        if request.url.path == "/repos/local/demo/commits":
            return httpx.Response(200, json=[{"sha": sha}])
        return httpx.Response(200, content=archive)
    workspace = EvolutionWorkspace(tmp_path / "external")
    provider = GitHubStagingMCPProvider(workspace=workspace, transport=httpx.MockTransport(handler))
    async def run():
        grant = enter_dispatch(DispatchGrant(
            principal_id="local_owner", capability_id=STAGE_CAPABILITY, tool_name=TOOL,
            risk_level="medium", approval_consumed=False,
        ))
        try:
            return await provider.call_tool(TOOL, {"repository": "local/demo"})
        finally:
            leave_dispatch(grant)
    manifest = asyncio.run(run())
    assert manifest["skipped_binaries"] == 2
    assert manifest["static_file_count"] == 2
    assert manifest["activation_performed"] is False
    assert manifest["execution_allowed"] is False
    assert not (workspace.root / "staging" / "local__demo" / "source" / "images").exists()


def test_size_aware_local_first_priority_and_existing_budget_retries(tmp_path):
    workspace = EvolutionWorkspace(tmp_path / "outside")
    calls = []

    class Gateway:
        async def invoke(self, request):
            calls.append(request)
            if request.capability_id == CAPABILITY_ID:
                return SimpleNamespace(decision=AuthorizationDecision.ALLOW, result={"items": []})
            assert request.capability_id == STAGE_CAPABILITY
            return SimpleNamespace(decision=AuthorizationDecision.ALLOW, result={
                "repository": request.arguments["repository"],
                "status": "READY_FOR_OWNER_REVIEW",
                "source_sha256": "b" * 64,
                "sandbox_attested": False, "activation_performed": False,
                "execution_allowed": False,
            })

    engine = SelfDiscoveryEngine(
        gateway=Gateway(), db_path=workspace.root / "catalog" / "proposals.sqlite3",
        workspace=workspace, auto_stage=True,
    )
    # New search yields zero entries, but a durable existing queue must progress.
    records = [
        ("local/huge-fastmcp", "Local fastmcp sqlite filesystem git zero API keys", 95000, None, None, 0),
        ("local/tiny-fastmcp", "Local fastmcp sqlite filesystem git zero API keys", 120, None, None, 0),
        ("local/small-budget", "Local fastmcp sqlite filesystem git zero API keys", 140, "STAGING_REJECTED", "GitHub download byte budget exceeded", 1),
        ("cloud/adapter", "Generic cloud connector", 10, None, None, 0),
        ("local/bad-source", "Local fastmcp sqlite filesystem git zero API keys", 90, "STAGING_REJECTED", "Static risk/paid API signature detected", 1),
    ]
    with sqlite3.connect(engine._db_path) as db:
        for i, (repo, desc, size_kb, status, reason, attempts) in enumerate(records):
            db.execute(
                "INSERT INTO evolution_proposals "
                "(proposal_id,repository,url,description,license,capability_hint,created_at,"
                "stars,size_kb,package_status,package_error,stage_attempts) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (f"p{i}", repo, "https://github.com/" + repo, desc, "MIT", "MCP", i,
                 150, size_kb, status, reason, attempts),
            )
    result = asyncio.run(engine.run_once())
    staged = [call.arguments["repository"] for call in calls
              if call.capability_id == STAGE_CAPABILITY]
    assert staged == ["local/tiny-fastmcp", "local/small-budget", "local/huge-fastmcp"]
    assert result["new_count"] == 0
    assert result["staging_attempted"] == result["staged_count"] == 3
    assert result["verified_count"] == 3
    assert engine.static_ready_count() == 3
    assert engine.proposals(20)[2]["package_status"] == "READY_FOR_OWNER_REVIEW"
    assert workspace.verified_packages() == []  # Gateway proof here is simulated; no files
    assert json.loads(workspace.active.read_text())["active"] == []
    # Ready records and security-policy rejections must never be restaged.
    second = asyncio.run(engine.run_once())
    assert second["staging_attempted"] == 1
    assert staged[0] == "local/tiny-fastmcp"


def test_local_rank_prefers_no_key_sqlite_over_generic_star_count():
    assert _local_rank("owner/sqlite-fastmcp", "zero API keys, local filesystem git", 10) > (
        _local_rank("owner/cloud", "generic connector", 100000)
    )
