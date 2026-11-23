"""Live recovery / quota regressions: no bypass of Owner, signed proof or Gateway."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aura_core.evolution import activation_runtime, attestor_worker, windows_job_mcp
from aura_core.evolution.activation_delegation import (
    SANDBOX_POLICY_SHA256, SANDBOX_TESTS_SHA256,
)
from aura_core.evolution.activation_runtime import DelegatedMCPActivationManager
from aura_core.evolution.external_staging import EvolutionWorkspace, StagingRejected
from aura_core.evolution.owner_cli import make_activation_delegation
from aura_core.evolution.sandbox_preflight import IsolatedMCPPreflight
from aura_core.evolution.windows_job_mcp import local_binding, verify_local
from aura_core.kernel.permissions import AuthorizationDecision
from aura_core.mcp.mcp_provider import MCPTool
from test_evolution_autonomous_activation import (
    _signed_fixture, _kernel, _request, FakeProvider,
)
from test_evolution_sandbox_preflight import _candidate


def run(awaitable):
    return asyncio.run(awaitable)


class WindowsOs:
    name = "nt"
    def __getattr__(self, key):
        return getattr(os, key)


def _local_owner_grant(workspace, monkeypatch):
    signer = Ed25519PrivateKey.generate()
    attestor = workspace._testing_attestor_signer
    owner_raw = signer.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    attestor_raw = attestor.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    grant = make_activation_delegation(
        signer, categories=("local_memory",), image=None,
        policy_sha256=SANDBOX_POLICY_SHA256, tests_sha256=SANDBOX_TESTS_SHA256,
        attestor_key_sha256=hashlib.sha256(attestor_raw).hexdigest(),
        attestor_runner_id="operator_runner", days=1, max_tools=2, min_score=70,
        allow_local_windows_process=True,
    )
    owner = workspace.root / "owner"
    (owner / "autonomous_delegation.pub.pem").write_bytes(
        signer.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    (owner / "autonomous_delegation.json").write_text(json.dumps(grant))
    monkeypatch.setenv("AURA_EVOLUTION_DELEGATION_KEY_SHA256",
                       hashlib.sha256(owner_raw).hexdigest())
    return attestor, grant


def test_signed_recoverable_quarantine_can_list_tools_and_activate_via_gateway(
    tmp_path, monkeypatch,
):
    workspace, name, repo = _signed_fixture(tmp_path, monkeypatch)
    _local_owner_grant(workspace, monkeypatch)
    # The original Docker proof is still signed under the previous Owner grant;
    # this regression uses the original valid Docker grant with a local Windows
    # authorization flag only for scan's explicitly opted-in recovery path.
    from aura_core.evolution.activation_delegation import ActivationDelegationVerifier
    new_grant = ActivationDelegationVerifier(workspace).verified_grant()
    assert new_grant is not None
    # Obtain a real Windows Job attestation against the newly signed grant.
    monkeypatch.setattr(attestor_worker, "os", WindowsOs())
    monkeypatch.setattr(activation_runtime, "os", WindowsOs())

    async def local_probe(self, package):
        assert package == name
        return {"status": "PREPARED_UNATTESTED", "tool_schemas": {
            "lookup_local": {"type": "object", "additionalProperties": False},
        }}
    monkeypatch.setattr(windows_job_mcp.LocalWindowsMCPPreflight, "probe", local_probe)
    signer = workspace._testing_attestor_signer
    run(attestor_worker.IndependentMCPAttestorWorker(
        workspace=workspace, key=signer,
    ).attest(name))

    # Real DockerMCPProvider._owner_authorized guard, not a provider_factory
    # shortcut: a fake only replaces the untrusted stdio transport.
    wire_sessions = []
    class Wire:
        def __init__(self):
            wire_sessions.append(self)
            self.closed = False
            self.calls = 0
        async def connect_stdio(self, parameters):
            assert parameters is not None
        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(
                name="lookup_local", input_schema={
                    "type": "object", "additionalProperties": False,
                },
            )])
        async def call_tool(self, name, arguments=None):
            self.calls += 1
            return {"local": True}
        async def close(self):
            self.closed = True

    monkeypatch.setattr(activation_runtime, "MCPConnection", Wire)
    monkeypatch.setattr(activation_runtime, "bridge_parameters",
                        lambda runtime, entry: SimpleNamespace(runtime=runtime, entry=entry))
    kernel, gateway = _kernel()
    manager = DelegatedMCPActivationManager(workspace=workspace, kernel=kernel)
    manager._persist(repo, "QUARANTINED", reason_code="PermissionError")
    assert manager._still_authorized(name) is False

    async def scenario():
        assert await manager.scan() == [repo]
        inventory = json.loads(workspace.active.read_text("utf-8"))["active"]
        assert len(inventory) == 1 and inventory[0]["status"] == "ACTIVE"
        assert not manager._recovering
        capability = inventory[0]["capabilities"][0]
        scope = "evolution:isolated:" + inventory[0]["source_sha256"] + ":lookup_local"
        allowed = await gateway.invoke(_request(capability, "lookup_local", scope))
        assert allowed.decision is AuthorizationDecision.ALLOW
        assert allowed.result == {"local": True}
        denied = await gateway.invoke(_request(capability, "lookup_local", scope,
                                               principal="not_the_owner"))
        assert denied.decision is AuthorizationDecision.DENY
        assert wire_sessions[0].calls == 1
        # Once ACTIVE, the temporary recovery exemption no longer exists.
        manager._persist(repo, "QUARANTINED", reason_code="PROVIDER_FAILED_OR_REVOKED")
        with pytest.raises(PermissionError, match="Quarantined"):
            await manager._active[name].provider.list_tools()
        await manager.close()

    run(scenario())


def test_signed_quota_deferred_candidate_is_reattested_and_signed_after_cleanup(
    tmp_path, monkeypatch,
):
    workspace, name, repo = _signed_fixture(tmp_path, monkeypatch)
    signer, grant_doc = _local_owner_grant(workspace, monkeypatch)
    monkeypatch.setattr(attestor_worker, "os", WindowsOs())
    seen = []
    async def local_probe(self, package):
        seen.append(package)
        return {"status": "PREPARED_UNATTESTED", "tool_schemas": {
            "lookup_local": {"type": "object", "additionalProperties": False},
        }}
    monkeypatch.setattr(windows_job_mcp.LocalWindowsMCPPreflight, "probe", local_probe)
    marker = workspace.root / "verified" / name / "local-windows-quarantined.json"
    marker.write_text(json.dumps({
        "status": "QUARANTINED", "reason_code": "SandboxUntrusted",
        "detail": "Evolution combined storage quota reached",
        "retry_count": 5, "recovery_epoch": "windows-isolated-wheels-20261122-v5",
    }), encoding="utf-8")
    worker = attestor_worker.IndependentMCPAttestorWorker(workspace=workspace, key=signer)
    result = run(worker.scan())
    assert result == [{
        "repository": repo, "attested_tools": 1, "independent_runner": "operator_runner",
    }]
    assert seen == [name]
    assert not marker.exists()
    payload = json.loads((workspace.root / "verified" / name /
                          "independent-attestations.json").read_text("utf-8"))
    assert payload["execution_profile"] == "windows-job-stdio"
    from aura_core.evolution.activation_runtime import runtime_fingerprint
    from aura_core.evolution.decision_engine import EvolutionDecisionEngine
    decision = EvolutionDecisionEngine(workspace).evaluate(name)
    tree = runtime_fingerprint(workspace, name)
    tool = MCPTool(
        name="lookup_local", description="",
        input_schema={"type": "object", "additionalProperties": False},
    )
    binding = local_binding(repository=repo, source_sha256=decision.source_sha256,
                            tree_sha256=tree, tool=tool, category=decision.category)
    proof = payload["tools"][0]["attestation"]
    assert verify_local(
        proof, key=signer.public_key(), grant=grant_doc["claims"],
        source_sha256=decision.source_sha256, tree_sha256=tree,
        binding_digest=binding,
    ) > 0
    # No stale retry counter can prevent future resource-driven re-evaluation.


def test_permanently_revoked_artifacts_reclaimed_before_runtime_quota(tmp_path):
    workspace = EvolutionWorkspace(tmp_path / "evolution", max_bytes=2_000_000)
    name, _ = _candidate(workspace)
    sandbox = IsolatedMCPPreflight(
        workspace, image="example/mcp@sha256:" + "a" * 64,
    )
    terminal = "retired__old"
    package = workspace.root / "verified" / terminal
    package.mkdir()
    (package / "source.zip").write_bytes(b"a" * 1_100_000)
    runtime = sandbox.runtime_root / terminal
    runtime.mkdir()
    (runtime / ".venv").mkdir()
    (runtime / ".venv" / "occupied.bin").write_bytes(b"x" * 1_300_000)
    workspace.active.write_text(json.dumps({
        "schema": "aura.external-capabilities.v1",
        "active": [{"repository": "retired/old", "status": "QUARANTINED",
                    "reason_code": "OWNER_REVOKED"}],
    }), encoding="utf-8")
    prepared, _, _ = sandbox.prepare(name)
    assert prepared.is_dir()
    assert not runtime.exists() and not (package / "source.zip").exists()
    log = (workspace.root / "logs" / "discovery.jsonl").read_text("utf-8")
    assert '"action": "quota_prune"' in log
    assert "OWNER_REVOKED" in workspace.active.read_text("utf-8")


def test_quota_cleanup_preserves_live_and_temporary_venvs(tmp_path):
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    sandbox = IsolatedMCPPreflight(
        workspace, image="example/mcp@sha256:" + "a" * 64,
    )
    for package_name in ("live__mcp", "deferred__mcp"):
        folder = workspace.root / "verified" / package_name
        folder.mkdir()
        (folder / "source.zip").write_bytes(b"z" * 1_200_000)
        runtime = sandbox.runtime_root / package_name
        runtime.mkdir()
        (runtime / "keep.bin").write_bytes(b"z" * 1024)
    (workspace.root / "verified" / "deferred__mcp" /
     "local-windows-quarantined.json").write_text(json.dumps({
         "status": "QUARANTINED", "reason_code": "SandboxUntrusted",
         "detail": "Evolution combined storage quota reached",
     }), encoding="utf-8")
    workspace.active.write_text(json.dumps({
        "schema": "aura.external-capabilities.v1",
        "active": [{"repository": "live/mcp", "status": "ACTIVE"}],
    }), encoding="utf-8")
    assert workspace.prune_permanent_evolution_artifacts() == 0
    for item in ("live__mcp", "deferred__mcp"):
        assert (sandbox.runtime_root / item / "keep.bin").exists()
        assert (workspace.root / "verified" / item / "source.zip").exists()


def test_quota_cleanup_rejects_symlink_escape_without_deleting_evidence(
    tmp_path,
):
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    sandbox = IsolatedMCPPreflight(
        workspace, image="example/mcp@sha256:" + "a" * 64,
    )
    folder = workspace.root / "verified" / "retired__bad"
    folder.mkdir()
    archive = folder / "source.zip"
    archive.write_bytes(b"archive" * 200_000)
    runtime = sandbox.runtime_root / "retired__bad"
    runtime.mkdir()
    outside = tmp_path / "sensitive"
    outside.write_text("keep", encoding="utf-8")
    try:
        (runtime / "shortcut").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Runner does not allow creating symlinks")
    workspace.active.write_text(json.dumps({
        "schema": "aura.external-capabilities.v1",
        "active": [{"repository": "retired/bad", "status": "REVOKED"}],
    }), encoding="utf-8")
    with pytest.raises(StagingRejected, match="link"):
        workspace.prune_permanent_evolution_artifacts()
    assert runtime.is_dir() and archive.is_file()
    assert outside.read_text("utf-8") == "keep"


def test_quota_default_is_bounded_for_isolated_windows_wheels(tmp_path, monkeypatch):
    monkeypatch.delenv("AURA_EVOLUTION_MAX_BYTES", raising=False)
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    assert workspace.max_bytes == 8 * 1024 ** 3
    with pytest.raises(ValueError, match="capacity"):
        EvolutionWorkspace(tmp_path / "oversized", max_bytes=11 * 1024 ** 3)
