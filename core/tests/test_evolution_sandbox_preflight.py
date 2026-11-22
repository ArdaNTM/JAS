"""Fail-closed isolated MCP sandbox preflight: no trusted attestations minted."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

from aura_core.evolution.external_staging import EvolutionWorkspace
from aura_core.evolution.sandbox_preflight import (
    IsolatedMCPPreflight, SandboxUntrusted,
)


def _candidate(workspace, *, entry="server.py", malicious=None):
    name = "demo__local-tool"
    package = workspace.root / "verified" / name
    package.mkdir()
    contents = {
        "README.md": b"Fully local offline MCP, no API key needed",
        "server.py": b"from fastmcp import FastMCP\napp = FastMCP('test')\n",
        "pyproject.toml": b"[project]\nname='demo-mcp'\n",
        "docs/README.md": b"documentation" * 20,
        "assets/icon.png": b"\x89PNG\x00",
    }
    if malicious:
        contents[malicious] = b"malicious"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
        for path, content in contents.items():
            z.writestr("root/" + path, content)
    archive = stream.getvalue()
    digest = hashlib.sha256(archive).hexdigest()
    (package / "source.zip").write_bytes(archive)
    (package / "aura-capability-manifest.json").write_text(json.dumps({
        "repository": "demo/local-tool", "source_sha256": digest,
        "status": "READY_FOR_OWNER_REVIEW",
        "license_spdx_metadata": "MIT", "entrypoint_hint": entry,
        "detected_capabilities": ["FastMCP"],
        "sandbox_attested": False, "activation_performed": False,
        "execution_allowed": False,
    }), encoding="utf-8")
    return name, archive


def test_prepare_extracts_only_static_safe_sources_outside_checkout(tmp_path):
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    name, archive = _candidate(workspace)
    sandbox = IsolatedMCPPreflight(
        workspace, image="example/fastmcp@sha256:" + "a" * 64,
    )
    root, entry, digest = sandbox.prepare(name)
    assert root.is_relative_to(workspace.root / "runtime")
    assert entry == "server.py"
    assert digest == hashlib.sha256(archive).hexdigest()
    assert (root / "server.py").is_file()
    assert not (root / "docs").exists()
    assert not (root / "assets").exists()
    report = json.loads((root / ".aura-untrusted-review.json").read_text())
    assert report["status"] == "PREPARED_UNATTESTED"
    assert report["execution_allowed"] is False
    assert json.loads(workspace.active.read_text())["active"] == []


def test_runtime_no_overwrite_and_digest_mismatch_deny(tmp_path):
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    name, _ = _candidate(workspace)
    sandbox = IsolatedMCPPreflight(workspace, image="example/mcp@sha256:" + "b" * 64)
    sandbox.prepare(name)
    with pytest.raises(SandboxUntrusted, match="already exists"):
        sandbox.prepare(name)
    (workspace.root / "verified" / name / "source.zip").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="SHA-256"):
        sandbox.prepare(name)


@pytest.mark.parametrize("image", [
    "latest", "example/python:latest", "--privileged",
    "example/tool@sha256:xxx", "example/tool@sha256:" + "g" * 64,
])
def test_unpinned_or_untrusted_image_rejected(tmp_path, image):
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    with pytest.raises(ValueError):
        IsolatedMCPPreflight(workspace, image=image)


def test_preflight_requires_hardened_no_network_containment(tmp_path):
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    sandbox = IsolatedMCPPreflight(workspace, image="python@sha256:" + "c" * 64)
    params = sandbox._docker_arguments(workspace.root / "runtime", "server.py")
    assert all(x in params for x in (
        "--network", "none", "--read-only", "--cap-drop", "ALL",
        "no-new-privileges", "--pids-limit", "--memory", "--cpus",
        "--user", "65534:65534", "readonly",
    ))
    assert "--privileged" not in params
    assert "host" not in params
    assert params[-2:] == ["-u", "server.py"]


def test_missing_sandbox_health_quarantines_without_registering(tmp_path, monkeypatch):
    import aura_core.evolution.sandbox_preflight as module
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    name, _ = _candidate(workspace)
    sandbox = IsolatedMCPPreflight(workspace, image="python@sha256:" + "d" * 64)
    monkeypatch.setattr(module.shutil, "which", lambda _: None)
    report = asyncio.run(sandbox.probe(name))
    assert report["status"] == "QUARANTINED"
    assert report["sandbox_attested"] is False
    assert report["activation_performed"] is False
    assert json.loads(workspace.active.read_text())["active"] == []
    audit = workspace.root / "logs" / "autonomous-preflight.jsonl"
    assert json.loads(audit.read_text().splitlines()[-1])["status"] == "QUARANTINED"


def test_successful_mock_stdio_still_is_unattested(tmp_path, monkeypatch):
    import aura_core.evolution.sandbox_preflight as module
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    name, _ = _candidate(workspace)

    class OfflineSession:
        async def connect_stdio(self, parameters):
            assert parameters.command == "docker"
            assert "--network" in parameters.args
        async def list_tools(self):
            return (SimpleNamespace(name="search_local",
                                    input_schema={"type": "object"}),)
        async def close(self):
            return None

    monkeypatch.setattr(module.shutil, "which", lambda _: "docker")
    monkeypatch.setattr(module, "MCPConnection", OfflineSession)
    sandbox = IsolatedMCPPreflight(workspace, image="example/mcp@sha256:" + "e" * 64)
    report = asyncio.run(sandbox.probe(name))
    assert report["status"] == "PREPARED_UNATTESTED"
    assert report["tool_count"] == 1
    assert report["sandbox_attested"] is False
    assert report["activation_performed"] is False
    assert json.loads(workspace.active.read_text())["active"] == []


def test_owner_cli_signs_review_only_and_revokes_without_core_rights():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from aura_core.evolution.owner_cli import make_review_delegation
    from aura_core.evolution.decision_engine import _canonical
    signer = Ed25519PrivateKey.generate()
    doc = make_review_delegation(
        signer, categories=("local_memory", "developer_tools"),
        duration_seconds=600, issued_at=100,
    )
    claims = doc["claims"]
    assert claims["scope"] == "static-review-only"
    assert claims["auto_activation"] is False
    assert claims["expires_at"] == 700
    import base64
    signature = base64.urlsafe_b64decode(doc["signature_b64"] + "==")
    signer.public_key().verify(signature, _canonical(claims))


@pytest.mark.parametrize("categories,days", [
    (("unauthorized",), 600),
    (("local_memory", "local_memory"), 600),
    (("local_memory",), 31 * 86400),
])
def test_owner_cli_invalid_delegation_denied(categories, days):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from aura_core.evolution.owner_cli import make_review_delegation
    with pytest.raises(ValueError):
        make_review_delegation(
            Ed25519PrivateKey.generate(), categories=categories,
            duration_seconds=days, issued_at=100,
        )
