"""External artifact staging never authorizes execution or writes in checkout."""
from __future__ import annotations

import asyncio
import io
import json
import os
import stat
import zipfile

import httpx
import pytest

from aura_core.evolution.external_staging import (
    CAPABILITY, TOOL, EvolutionWorkspace, GitHubStagingMCPProvider,
    StagingRejected, _validated_files,
)
from aura_core.mcp.dispatch_context import DispatchGrant, enter_dispatch, leave_dispatch


def _zip(files):
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, data in files.items():
            bundle.writestr(name, data)
    return memory.getvalue()


def _valid_archive():
    return _zip({
        "worker-abc/server.py": "from fastmcp import FastMCP\napp = FastMCP('demo')\n",
        "worker-abc/README.md": "Fully local and offline MCP tool.\n",
        "worker-abc/pyproject.toml": "[project]\nname = 'demo'\n",
    })


def _transport(archive=None, license_id="MIT"):
    archive = archive if archive is not None else _valid_archive()
    def handler(request):
        assert request.url.host in ("api.github.com", "codeload.github.com")
        if request.url.path == "/repos/sample/worker":
            return httpx.Response(200, json={
                "full_name": "sample/worker", "private": False, "fork": False,
                "archived": False, "license": {"spdx_id": license_id},
                "description": "Offline MCP Python tools",
            })
        if request.url.path == "/repos/sample/worker/commits":
            return httpx.Response(200, json=[{"sha": "a" * 40}])
        if request.url.path == "/sample/worker/zip/" + ("a" * 40):
            return httpx.Response(200, content=archive)
        raise AssertionError("Unexpected GitHub URL: " + str(request.url))
    return httpx.MockTransport(handler)


def _authorized(provider, name="sample/worker"):
    token = enter_dispatch(DispatchGrant(
        principal_id="local_owner", capability_id=CAPABILITY,
        tool_name=TOOL, risk_level="medium", approval_consumed=False,
    ))
    try:
        return asyncio.run(provider.call_tool(TOOL, {"repository": name}))
    finally:
        leave_dispatch(token)


def test_inert_mcp_stage_uses_gateway_context(tmp_path):
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    provider = GitHubStagingMCPProvider(workspace=workspace, transport=_transport())
    with pytest.raises(PermissionError):
        asyncio.run(provider.call_tool(TOOL, {"repository": "sample/worker"}))
    result = _authorized(provider)
    assert result["repository"] == "sample/worker"
    assert result["license_spdx_metadata"] == "MIT"
    assert result["status"] == "READY_FOR_OWNER_REVIEW"
    assert result["sandbox_attested"] is False
    assert result["owner_approved"] is False
    assert result["activation_performed"] is False
    assert result["capability_registered"] is False
    assert result["execution_allowed"] is False
    assert result["git_commit_sha"] == "a" * 40
    package = workspace.root / "verified" / "sample__worker"
    assert (package / "source.zip").is_file()
    assert json.loads((package / "aura-capability-manifest.json").read_text()) == result
    assert (workspace.root / "staging" / "sample__worker" / "source"
            / "server.py").is_file()
    assert json.loads(workspace.active.read_text())["active"] == []
    assert (workspace.root / "logs").is_dir()
    assert workspace.root != tmp_path.parents[2]
    assert _authorized(provider)["source_sha256"] == result["source_sha256"]


@pytest.mark.parametrize("filename", [
    "worker-abc/../../evil.py",
    "worker-abc/C:\\evil.py",
    "worker-abc/CON.txt",
    "worker-abc/src/../server.py",
    "worker-abc/SERVER.PY",
])
def test_rejects_unsafe_archive_paths(filename):
    archive = _zip({"worker-abc/server.py": "pass\n", filename: "pass\n"})
    if filename.endswith("SERVER.PY"):
        # Case fold conflict with server.py must reject.
        archive = _zip({"worker-abc/server.py": "pass\n",
                        "worker-abc/SERVER.PY": "pass\n"})
    with pytest.raises(StagingRejected):
        _validated_files(archive)


def test_rejects_zip_symlinks_and_unsafe_python():
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w") as bundle:
        info = zipfile.ZipInfo("worker-abc/server.py")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        bundle.writestr(info, "destination")
    with pytest.raises(StagingRejected):
        _validated_files(memory.getvalue())
    with pytest.raises(StagingRejected, match="Static risk"):
        _validated_files(_zip({
            "worker-abc/server.py": "import os\nos.system('bad')\n",
            "worker-abc/README.md": "Fully local and offline",
        }))


def test_no_paid_api_or_macos_and_no_executable(tmp_path):
    provider = GitHubStagingMCPProvider(
        workspace=EvolutionWorkspace(tmp_path / "evolution"),
        transport=_transport(license_id="GPL-3.0"),
    )
    with pytest.raises(StagingRejected, match="metadata/license"):
        _authorized(provider)
    for file in ("worker-abc/README.md", "worker-abc/pyproject.toml"):
        files = {"worker-abc/server.py": "pass\n", file: "Requires Xcode and SwiftUI"}
        with pytest.raises(StagingRejected):
            _validated_files(_zip(files))


def test_no_symlink_root_no_inside_checkout_and_quota(tmp_path):
    with pytest.raises(ValueError):
        EvolutionWorkspace("relative-evolution")
    workspace = EvolutionWorkspace(tmp_path / "evolution", max_items=1,
                                   max_bytes=1_000_000)
    with pytest.raises(StagingRejected, match="quota"):
        workspace.reserve("sample/worker", 2_000_000)
    (workspace.root / "verified" / "existing").mkdir()
    with pytest.raises(StagingRejected, match="count quota"):
        workspace.reserve("sample/other", 100)
    link = tmp_path / "symlink-root"
    try:
        link.symlink_to(workspace.root, target_is_directory=True)
    except (NotImplementedError, OSError):
        return
    with pytest.raises(StagingRejected, match="Symlink"):
        EvolutionWorkspace(link)


def test_archive_requires_real_entrypoint_and_bounded_zip():
    with pytest.raises(StagingRejected, match="entrypoint"):
        _validated_files(_zip({"worker-abc/README.md": "fully local offline"}))
    with pytest.raises(StagingRejected, match="budget"):
        _validated_files(b"x" * 3_000_001)
    with pytest.raises(StagingRejected):
        _validated_files(_zip({"worker-abc/server.py": "a" * 200_000}))


def test_no_misleading_repo_with_missing_readme_is_statically_eligible():
    with pytest.raises(StagingRejected, match="README"):
        _validated_files(_zip({"worker-abc/server.py": "from fastmcp import FastMCP"}))
    with pytest.raises(StagingRejected, match="multiple source roots"):
        _validated_files(_zip({
            "worker-abc/server.py": "pass\n",
            "other/README.md": "offline locally",
        }))


def test_no_untrusted_remote_metadata_can_escape_fixed_api(tmp_path):
    provider = GitHubStagingMCPProvider(
        workspace=EvolutionWorkspace(tmp_path / "external"),
        transport=_transport(),
    )
    for repo in ("http://127.0.0.1", "sample/../worker",
                 "sample\\worker", "a/worker?ref=evil"):
        with pytest.raises(StagingRejected):
            _authorized(provider, repo)


def test_audit_logs_only_bounded_metadata_and_rejects_symlink(tmp_path):
    workspace = EvolutionWorkspace(tmp_path / "safe")
    workspace.audit(action="stage_verified", repository="sample/worker",
                    result="OWNER_REVIEW_REQUIRED")
    rows = (workspace.root / "logs" / "discovery.jsonl").read_text().splitlines()
    assert len(rows) == 1
    assert json.loads(rows[0])["repository"] == "sample/worker"
    with pytest.raises(ValueError):
        workspace.audit(action="stage_verified", repository="../bad",
                        result="OWNER_REVIEW_REQUIRED")


def test_read_only_verified_inventory_never_grants_activation(tmp_path):
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    provider = GitHubStagingMCPProvider(workspace=workspace, transport=_transport())
    _authorized(provider)
    packages = workspace.verified_packages()
    assert len(packages) == 1
    assert packages[0]["repository"] == "sample/worker"
    assert packages[0]["sandbox_attested"] is False
    assert packages[0]["activation_performed"] is False


def test_external_evolution_root_never_equals_checkout():
    from pathlib import Path
    checkout = Path(__file__).resolve().parents[2]
    with pytest.raises(PermissionError, match="outside JAS checkout"):
        EvolutionWorkspace(checkout)
    with pytest.raises(PermissionError, match="outside JAS checkout"):
        EvolutionWorkspace(checkout / "core" / "test-secret")


def test_real_github_style_zip_root_directory_is_not_rejected():
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("worker-abc/", "")
        bundle.writestr("worker-abc/server.py", "from fastmcp import FastMCP\n")
        bundle.writestr("worker-abc/README.md", "Fully local and offline")
    files, entrypoint = _validated_files(memory.getvalue())
    assert entrypoint == "server.py"
    assert "README.md" in files


def test_repository_traversal_names_are_denied_before_url_build(tmp_path):
    workspace = EvolutionWorkspace(tmp_path / "workspace")
    provider = GitHubStagingMCPProvider(workspace=workspace, transport=_transport())
    for name in ("../bad", "good/..", "./repo", "good/.", "good./repo"):
        with pytest.raises((StagingRejected, ValueError)):
            _authorized(provider, name)
    assert workspace.verified_packages() == []



def test_staging_repo_metadata_accepts_300k_with_2m_cap(tmp_path):
    from aura_core.evolution.self_discovery import GITHUB_RESPONSE_MAX_BYTES
    assert GITHUB_RESPONSE_MAX_BYTES == 2_097_152
    archive = _valid_archive()
    def handler(request):
        if request.url.path == "/repos/sample/worker":
            return httpx.Response(200, json={
                "full_name": "sample/worker", "private": False,
                "fork": False, "archived": False,
                "license": {"spdx_id": "MIT"}, "description": "Offline MCP",
                "padding": "x" * 300_000,
            })
        if request.url.path == "/repos/sample/worker/commits":
            return httpx.Response(200, json=[{"sha": "a" * 40}])
        if request.url.path == "/sample/worker/zip/" + ("a" * 40):
            return httpx.Response(200, content=archive)
        raise AssertionError("Unexpected remote path")
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    provider = GitHubStagingMCPProvider(
        workspace=workspace, transport=httpx.MockTransport(handler),
    )
    result = _authorized(provider)
    assert result["status"] == "READY_FOR_OWNER_REVIEW"
    assert result["execution_allowed"] is False


def test_staging_repo_metadata_over_2m_remains_rejected(tmp_path):
    from aura_core.evolution.self_discovery import GITHUB_RESPONSE_MAX_BYTES
    def handler(request):
        assert request.url.path == "/repos/sample/worker"
        return httpx.Response(200, content=b"x" * (GITHUB_RESPONSE_MAX_BYTES + 1))
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    provider = GitHubStagingMCPProvider(
        workspace=workspace, transport=httpx.MockTransport(handler),
    )
    with pytest.raises(StagingRejected, match="budget"):
        _authorized(provider)
    assert workspace.verified_packages() == []



def test_scoped_local_owner_policy_and_real_gateway_end_to_end(tmp_path):
    from aura_core.evolution.external_staging import (
        local_staging_policy, staging_scope,
    )
    from aura_core.kernel.services import ServiceRegistry, ServiceDefinition, ServiceCategory
    from aura_core.kernel.capabilities import (
        CapabilityRegistry, CapabilityDefinition, ProviderType, CapabilityCategory,
    )
    from aura_core.kernel.permissions import (
        PermissionEngine, AuthorizationDecision, RiskLevel,
    )
    from aura_core.mcp.provider import ProviderRegistry, ProviderDefinition
    from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest

    workspace = EvolutionWorkspace(tmp_path / "evolution")
    provider = GitHubStagingMCPProvider(
        workspace=workspace, transport=_transport(),
    )
    services = ServiceRegistry()
    service = services.register(ServiceDefinition(
        name="test-static-staging", version="1.0.0", provider="aura",
        category=ServiceCategory.MCP, capabilities=frozenset({CAPABILITY}),
    ), provider)
    providers = ProviderRegistry(services)
    providers.register(ProviderDefinition(
        provider_id="aura.test-static-staging", name="Test Static Staging",
        version="1.0.0", service_id=service.service_id,
    ), provider)
    capabilities = CapabilityRegistry(services)
    capabilities.register(CapabilityDefinition(
        capability_id=CAPABILITY, name="Bounded External Static Staging",
        version="1.0.0", description="Inert external local code static inspection",
        provider_id="aura.test-static-staging", provider_type=ProviderType.MCP,
        category=CapabilityCategory.SECURITY, tool_name=TOOL,
        risk_level="medium", required_permissions=frozenset({CAPABILITY}),
    ))
    permissions = PermissionEngine(capabilities)
    permissions.add_policy(local_staging_policy(workspace))
    gateway = MCPGateway(
        capability_registry=capabilities, provider_registry=providers,
        permission_engine=permissions,
    )

    def request(*, principal="local_owner", scope=None):
        return MCPGatewayRequest(
            request_id="unique-staging-test",
            principal_id=principal, capability_id=CAPABILITY,
            operation_id=CAPABILITY, resource_scope=scope or staging_scope(workspace),
            risk_level=RiskLevel.MEDIUM, tool_name=TOOL,
            arguments={"repository": "sample/worker"},
        )
    for principal, scope in (
        ("stranger", staging_scope(workspace)),
        ("local_owner", str(workspace.root / "verified")),
        ("local_owner", str(workspace.root / "staging-sibling")),
    ):
        response = _run(gateway.invoke(request(principal=principal, scope=scope)))
        assert response.decision is AuthorizationDecision.DENY
        assert not list((workspace.root / "verified").iterdir())

    accepted = _run(gateway.invoke(request()))
    assert accepted.decision is AuthorizationDecision.ALLOW
    assert accepted.result["status"] == "READY_FOR_OWNER_REVIEW"
    assert (workspace.root / "staging" / "sample__worker" / "source.zip").is_file()
    assert (workspace.root / "verified" / "sample__worker"
            / "aura-capability-manifest.json").is_file()
    assert __import__("json").loads(workspace.active.read_text())["active"] == []


def test_staging_rejections_are_audited_without_activation(tmp_path):
    ws = EvolutionWorkspace(tmp_path / "outside")
    ws.audit_rejection("owner/mcp-repo", "Mandatory external API key required")
    obj = json.loads(
        (ws.root / "logs" / "staging-rejections.jsonl").read_text().splitlines()[0]
    )
    assert obj["status"] == "STAGING_REJECTED"
    assert obj["repository"] == "owner/mcp-repo"
    assert "API key required" in obj["reason"]
    assert json.loads(ws.active.read_text())["active"] == []
