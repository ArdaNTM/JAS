"""Expiry/restage regressions: no external tool execution or Owner bypass."""
from __future__ import annotations

import asyncio
import hashlib
import sqlite3
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from aura_core.application.api import create_api
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig
from aura_core.evolution.activation_runtime import (
    DelegatedMCPActivationManager, DockerMCPProvider, _Live,
)
from aura_core.evolution.external_staging import EvolutionWorkspace, CAPABILITY as STAGE_CAPABILITY
from aura_core.evolution.self_discovery import SelfDiscoveryEngine
from aura_core.kernel.capabilities import ProviderType
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.mcp.connection import MCPConnection


@pytest.mark.parametrize("method", ["list_tools", "call_tool"])
def test_expired_live_mcp_retires_to_waiting_without_scan(tmp_path, method):
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    kernel = SimpleNamespace(
        event_bus=None, permission_engine=Mock(), capability_registry=Mock(),
        provider_registry=Mock(), service_registry=Mock(),
    )
    manager = DelegatedMCPActivationManager(workspace=workspace, kernel=kernel)
    manager.delegation = SimpleNamespace(verified_grant=lambda: {"signed": True})
    repository = "example/localmcp"
    package = repository.replace("/", "__")
    runtime = workspace.root / "runtime" / package
    runtime.mkdir(parents=True)
    expired = int(time.time()) - 10
    retired = []
    failures = Mock()

    def on_expired(name):
        retired.append(asyncio.create_task(manager._expire(name)))

    provider = DockerMCPProvider(
        MCPConnection(), runtime=runtime, archive_sha256="",
        workspace=workspace, package=package, on_failure=failures,
        owner_authorized=lambda: True, attestation_expires_at=expired,
        on_expired=on_expired,
    )
    provider.close = AsyncMock()
    manager._active[package] = _Live(
        provider, "external.example", "external.service", ("external.cap",),
        ("owner.policy",), "local_memory", expired,
    )
    manager._persist(repository, "ACTIVE", attestation_expires_at=expired)

    async def exercise():
        with pytest.raises(PermissionError, match="attestation expired"):
            if method == "list_tools":
                await provider.list_tools()
            else:
                await provider.call_tool("remember", {"text": "private"})
        await asyncio.gather(*retired)
        # Repeated calls to the retired connection cannot schedule quarantine.
        with pytest.raises(PermissionError):
            await provider.list_tools()

    asyncio.run(exercise())
    row = next(item for item in manager._load_inventory()["active"]
               if item["repository"] == repository)
    assert row["status"] == "WAITING_ATTESTATION"
    assert row["reason_code"] == "EXPIRED_ATTESTATION"
    assert row["reason_detail"] == "Signed evidence expired; awaiting independent renewal"
    assert package not in manager._active
    assert runtime.is_dir()  # Expiry must not delete prepared runtime/evidence.
    provider.close.assert_awaited_once()
    kernel.permission_engine.revoke_policy.assert_called_once_with("owner.policy")
    kernel.capability_registry.unregister.assert_called_once()
    failures.assert_not_called()


def test_owner_rejection_is_still_a_failure_not_expiry(tmp_path):
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    failure = Mock()
    provider = DockerMCPProvider(
        MCPConnection(), runtime=workspace.root / "runtime" / "example__local",
        archive_sha256="", workspace=workspace, package="example__local",
        on_failure=failure, owner_authorized=lambda: False,
        attestation_expires_at=int(time.time()) + 600,
    )
    with pytest.raises(PermissionError, match="revoked"):
        asyncio.run(provider.list_tools())
    failure.assert_called_once_with("example__local")


def test_expired_provider_permissionerror_does_not_make_task_plan_500(monkeypatch):
    monkeypatch.setenv("AURA_ASSISTANT_AUTO_TOOLS_ENABLED", "1")
    monkeypatch.setenv("AURA_TELEMETRY_DAEMON_ENABLED", "0")
    app = create_api(
        RuntimeConfig(runtime="ollama", model="qwen3", temperature=0.7, max_tokens=32),
        backend_config=BackendConfig(endpoint="http://127.0.0.1:11434", timeout=30.0),
    )
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "local_owner"

    class ExpiredProvider:
        async def list_tools(self):
            raise PermissionError("External provider attestation expired")

    definition = SimpleNamespace(
        capability_id="external.mcp.example.remember", provider_id="external.example",
        provider_type=ProviderType.MCP, tool_name="remember", risk_level="low",
    )
    record = SimpleNamespace(definition=definition, available=True, healthy=True)
    provider = ExpiredProvider()
    app.state.kernel = SimpleNamespace(
        capability_registry=SimpleNamespace(records=lambda: (record,)),
        provider_registry=SimpleNamespace(resolve=lambda provider_id: provider),
    )
    def no_matching_capability(_directive):
        raise ValueError("No governed capability matches")
    app.state.directive_planner = SimpleNamespace(plan=no_matching_capability)

    with TestClient(app, headers={"Authorization": "Bearer " + "t" * 40},
                    raise_server_exceptions=False) as client:
        response = client.post("/api/tasks/plan", json={"directive": "unsupported_tool_action"})
    assert response.status_code == 200, response.text
    assert response.json() == {"resource_scope": "local-assistant", "steps": []}


@pytest.mark.parametrize("missing", [True, False])
def test_ready_candidate_requeues_only_if_archive_missing_or_mismatched(tmp_path, missing):
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    repository = "sample/localmemory"
    archive = workspace.root / "verified" / "sample__localmemory" / "source.zip"
    archive.parent.mkdir(parents=True)
    expected_bytes = b"original pinned source archive"
    expected_sha = hashlib.sha256(expected_bytes).hexdigest()
    if not missing:
        archive.write_bytes(expected_bytes)

    class StageGateway:
        def __init__(self):
            self.calls = []

        async def invoke(self, request):
            self.calls.append(request)
            assert request.capability_id == STAGE_CAPABILITY
            assert request.risk_level is RiskLevel.MEDIUM
            with sqlite3.connect(engine._db_path) as db:
                row = db.execute(
                    "SELECT package_status,source_sha256 FROM evolution_proposals "
                    "WHERE repository=?", (repository,),
                ).fetchone()
            assert row == (None, None)
            archive.write_bytes(expected_bytes)
            return SimpleNamespace(decision=AuthorizationDecision.ALLOW, result={
                "repository": repository, "status": "READY_FOR_OWNER_REVIEW",
                "source_sha256": expected_sha, "sandbox_attested": False,
                "activation_performed": False, "execution_allowed": False,
            })

    gateway = StageGateway()
    engine = SelfDiscoveryEngine(
        gateway=gateway, db_path=workspace.root / "catalog" / "proposals.sqlite3",
        workspace=workspace, auto_stage=True,
    )
    with sqlite3.connect(engine._db_path) as db:
        db.execute(
            "INSERT INTO evolution_proposals "
            "(proposal_id,repository,url,description,license,capability_hint,"
            "status,created_at,stars,size_kb,package_status,source_sha256) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("example", repository, "https://github.com/" + repository,
             "Offline MCP", "MIT", "Python MCP",
             "pending_owner_review", 1.0, 100, 10,
             "READY_FOR_OWNER_REVIEW", expected_sha),
        )
    result = asyncio.run(engine._stage_pending())
    assert result["attempted"] == (1 if missing else 0)
    assert len(gateway.calls) == (1 if missing else 0)
    assert engine.proposals()[0]["package_status"] == "READY_FOR_OWNER_REVIEW"
    assert asyncio.run(engine._stage_pending())["attempted"] == 0


def test_corrupt_cached_archive_requires_restage_not_stale_ready(tmp_path):
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    repository = "sample/memory"
    archive = workspace.root / "verified" / "sample__memory" / "source.zip"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"tampered archive")
    calls = []

    class DeniedGateway:
        async def invoke(self, request):
            calls.append(request)
            return SimpleNamespace(decision=AuthorizationDecision.DENY, result=None)

    engine = SelfDiscoveryEngine(
        gateway=DeniedGateway(), db_path=workspace.root / "catalog" / "proposals.sqlite3",
        workspace=workspace, auto_stage=True,
    )
    with sqlite3.connect(engine._db_path) as db:
        db.execute(
            "INSERT INTO evolution_proposals "
            "(proposal_id,repository,url,description,license,capability_hint,"
            "status,created_at,stars,size_kb,package_status,source_sha256) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("tampered", repository, "https://github.com/" + repository,
             "Offline MCP", "MIT", "Python MCP",
             "pending_owner_review", 1.0, 100, 10,
             "READY_FOR_OWNER_REVIEW", hashlib.sha256(b"original").hexdigest()),
        )
    result = asyncio.run(engine._stage_pending())
    assert result["attempted"] == 1
    assert len(calls) == 1
    assert engine.proposals()[0]["package_status"] == "STAGING_REJECTED"
    assert engine.static_ready_count() == 0
    assert asyncio.run(engine._stage_pending())["attempted"] == 0
