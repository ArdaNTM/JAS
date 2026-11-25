"""Post-PR187/188 live regressions: signed activation, nonblocking startup, queue."""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from types import SimpleNamespace

import pytest

from aura_core.evolution.activation_runtime import DelegatedMCPActivationManager
from aura_core.evolution.continuous_evolution import ContinuousEvolutionController
from aura_core.evolution.self_discovery import (
    CATALOG_CAPABILITY, CAPABILITY_ID, SelfDiscoveryEngine, DiscoveryUnavailable,
)
from aura_core.kernel.permissions import AuthorizationDecision


def run(coro):
    return asyncio.run(coro)


def test_activation_failure_records_bounded_reason_in_inventory_and_jsonl(
    tmp_path, monkeypatch,
):
    from test_evolution_autonomous_activation import _signed_fixture, _kernel

    workspace, name, repo = _signed_fixture(tmp_path, monkeypatch)
    kernel, _ = _kernel()
    manager = DelegatedMCPActivationManager(
        workspace=workspace, kernel=kernel,
        provider_factory=lambda *_: None,
    )
    bundle = workspace.root / "verified" / name / "independent-attestations.json"
    data = json.loads(bundle.read_text("utf-8"))
    data["runtime_tree_sha256"] = "0" * 64
    bundle.write_text(json.dumps(data), encoding="utf-8")

    assert run(manager.scan()) == []
    row = json.loads(workspace.active.read_text("utf-8"))["active"][0]
    assert row["status"] == "QUARANTINED"
    assert row["reason_code"] == "PermissionError"
    assert row["reason_detail"] == "Untrusted sandbox bundle"
    audit = (workspace.root / "logs" / "autonomous-activations.jsonl")
    event = json.loads(audit.read_text("utf-8").splitlines()[-1])
    assert event["repository"] == repo
    assert event["reason_detail"] == row["reason_detail"]
    assert len(event["reason_detail"]) <= 160


def test_reason_detail_redacts_secrets_and_paths(tmp_path):
    from aura_core.evolution.external_staging import EvolutionWorkspace
    from test_evolution_autonomous_activation import _kernel

    workspace = EvolutionWorkspace(tmp_path / "evolution")
    manager = DelegatedMCPActivationManager(
        workspace=workspace, kernel=_kernel()[0],
    )
    manager._persist(
        "riponcm/projectmem", "WAITING_ATTESTATION", reason_code="PermissionError",
        reason_detail="Access to C:\\Users\\OWNER\\sensitive\\key.pem denied; token=topsecret\r\nbad",
    )
    record = json.loads(workspace.active.read_text("utf-8"))["active"][0]
    logged = json.loads(
        (workspace.root / "logs" / "autonomous-activations.jsonl").read_text("utf-8")
    )
    assert record["reason_detail"] == logged["reason_detail"]
    assert "topsecret" not in record["reason_detail"]
    assert "OWNER" not in record["reason_detail"]
    assert "\n" not in record["reason_detail"]
    assert len(record["reason_detail"]) <= 160


def test_delegated_manager_start_is_nonblocking_while_scan_waits(
    tmp_path, monkeypatch,
):
    from test_evolution_autonomous_activation import _signed_fixture, _kernel

    workspace, _, _ = _signed_fixture(tmp_path, monkeypatch)
    manager = DelegatedMCPActivationManager(workspace=workspace, kernel=_kernel()[0])

    async def scenario():
        blocked = asyncio.Event()
        entered = asyncio.Event()

        async def slow_scan(*, limit=3):
            entered.set()
            await blocked.wait()
            return []

        monkeypatch.setattr(manager, "scan", slow_scan)
        await asyncio.wait_for(manager.start(), timeout=0.2)
        await asyncio.wait_for(entered.wait(), timeout=0.2)
        # External MCP handshake may remain blocked while Core can serve /health.
        assert manager._task is not None and not manager._task.done()
        blocked.set()
        await asyncio.wait_for(manager.close(), timeout=0.2)
    run(scenario())


def test_local_windows_attestor_signed_projectmem_activates_without_bypass(
    tmp_path, monkeypatch,
):
    """Real Ed25519 attestation and policy verification; only stdio is inert."""
    import hashlib
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from aura_core.evolution import activation_runtime, attestor_worker, windows_job_mcp
    from aura_core.evolution.activation_delegation import (
        SANDBOX_POLICY_SHA256, SANDBOX_TESTS_SHA256,
    )
    from aura_core.evolution.owner_cli import make_activation_delegation
    from aura_core.mcp.mcp_provider import MCPTool
    from test_evolution_autonomous_activation import (
        _signed_fixture, _kernel, FakeProvider,
    )

    workspace, old_name, old_repo = _signed_fixture(tmp_path, monkeypatch)
    name, repo = "riponcm__projectmem", "riponcm/projectmem"
    (workspace.root / "verified" / old_name).rename(workspace.root / "verified" / name)
    (workspace.root / "runtime" / old_name).rename(workspace.root / "runtime" / name)
    manifest = workspace.root / "verified" / name / "aura-capability-manifest.json"
    metadata = json.loads(manifest.read_text("utf-8"))
    metadata["repository"] = repo
    manifest.write_text(json.dumps(metadata), encoding="utf-8")

    owner = Ed25519PrivateKey.generate()
    attestor = workspace._testing_attestor_signer
    owner_raw = owner.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    attestor_raw = attestor.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    grant = make_activation_delegation(
        owner, categories=("local_memory",), image=None,
        policy_sha256=SANDBOX_POLICY_SHA256,
        tests_sha256=SANDBOX_TESTS_SHA256,
        attestor_key_sha256=hashlib.sha256(attestor_raw).hexdigest(),
        attestor_runner_id="operator_runner",
        days=1, max_tools=2, min_score=70,
        allow_local_windows_process=True,
    )
    owner_dir = workspace.root / "owner"
    (owner_dir / "autonomous_delegation.pub.pem").write_bytes(
        owner.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    (owner_dir / "autonomous_delegation.json").write_text(json.dumps(grant))
    monkeypatch.setenv("AURA_EVOLUTION_DELEGATION_KEY_SHA256",
                       hashlib.sha256(owner_raw).hexdigest())

    # Avoid patching process-global os.name, which breaks pathlib on Linux CI.
    class WindowsOs:
        name = "nt"

        def __getattr__(self, member):
            return getattr(os, member)

    for module in (activation_runtime, attestor_worker):
        monkeypatch.setattr(module, "os", WindowsOs())
    async def preflight_stub(self, package):
        assert package == name
        return {
            "status": "PREPARED_UNATTESTED",
            "source_sha256": metadata["source_sha256"],
            "runtime_tree_sha256": activation_runtime.runtime_fingerprint(workspace, name),
            "tool_schemas": {
                "lookup_local": {"type": "object", "additionalProperties": False},
            },
        }

    monkeypatch.setattr(windows_job_mcp.LocalWindowsMCPPreflight,
                        "probe", preflight_stub)
    kernel, _ = _kernel()
    async def factory(*_):
        return FakeProvider()
    manager = DelegatedMCPActivationManager(
        workspace=workspace, kernel=kernel, provider_factory=factory,
    )

    async def scenario():
        worker = attestor_worker.IndependentMCPAttestorWorker(
            workspace=workspace, key=attestor,
        )
        evidence = await worker.attest(name)
        assert evidence["repository"] == repo
        assert await manager.scan() == [repo]
        active = json.loads(workspace.active.read_text("utf-8"))["active"][0]
        assert active["status"] == "ACTIVE" and active["capabilities"]
        assert kernel.capability_registry.records()
        await manager.close()

    run(scenario())


class PartialGateway:
    def __init__(self):
        self.calls = []

    async def invoke(self, request):
        self.calls.append(request)
        if request.capability_id == CAPABILITY_ID:
            raise DiscoveryUnavailable("GitHub rate limit reached")
        if request.capability_id == CATALOG_CAPABILITY:
            if request.arguments["source"] == "pypi":
                raise DiscoveryUnavailable("PyPI timed out")
            return SimpleNamespace(decision=AuthorizationDecision.ALLOW, result={
                "items": [{"repository": "riponcm/projectmem",
                           "url": "https://github.com/riponcm/projectmem",
                           "description": "local memory offline", "license": "MIT",
                           "stars": 11, "size_kb": 99, "capability_hint": "FastMCP"}],
            })
        return SimpleNamespace(decision=AuthorizationDecision.ALLOW, result={
            "status": "READY_FOR_OWNER_REVIEW", "repository": "riponcm/projectmem",
            "source_sha256": "a" * 64,
            "sandbox_attested": False,
            "activation_performed": False, "execution_allowed": False,
        })


def test_multisource_partial_failure_stages_previous_null_queue_and_reports_health(
    tmp_path,
):
    from aura_core.evolution.external_staging import EvolutionWorkspace
    workspace = EvolutionWorkspace(tmp_path / "outside")
    gateway = PartialGateway()
    engine = SelfDiscoveryEngine(
        gateway=gateway, workspace=workspace, auto_stage=True,
        db_path=workspace.root / "catalog" / "proposals.sqlite3",
    )
    with engine._connect() as db:
        db.execute(
            "INSERT INTO evolution_proposals"
            "(proposal_id, repository, url, description, license, capability_hint, created_at)"
            "VALUES (?,?,?,?,?,?,?)",
            ("legacy1", "riponcm/projectmem", "https://github.com/riponcm/projectmem",
             "local Python MCP", "MIT", "FastMCP", 1.0),
        )
    result = run(engine.run_once(multi_source=True))
    assert result["staged_count"] == 1
    assert result["new_count"] == 0
    assert set(result["source_health"]) == {"github", "registry", "pypi"}
    assert result["source_health"]["registry"]["state"] == "OK"
    assert result["source_health"]["pypi"]["state"] == "UNAVAILABLE"
    assert result["source_health"]["github"]["state"] == "UNAVAILABLE"
    with engine._connect() as db:
        assert db.execute(
            "SELECT package_status FROM evolution_proposals WHERE repository=?",
            ("riponcm/projectmem",),
        ).fetchone()[0] == "READY_FOR_OWNER_REVIEW"
    controller = ContinuousEvolutionController(discovery=engine)
    assert controller.status()["source_health"] == result["source_health"]
    from aura_core.evolution.external_staging import CAPABILITY as STAGE_CAPABILITY
    assert all(request.capability_id in {CAPABILITY_ID, CATALOG_CAPABILITY, STAGE_CAPABILITY}
               for request in gateway.calls)



def test_local_scratch_keeps_runtime_fingerprint_immutable_and_fails_closed(
    tmp_path, monkeypatch,
):
    from test_evolution_autonomous_activation import _signed_fixture
    from aura_core.evolution.activation_runtime import runtime_fingerprint
    from aura_core.evolution.sandbox_preflight import (
        local_job_scratch_root, SandboxUntrusted,
    )

    workspace, name, _ = _signed_fixture(tmp_path, monkeypatch)
    before = runtime_fingerprint(workspace, name)
    scratch = local_job_scratch_root(workspace, name)
    assert scratch.is_relative_to(workspace.root)
    assert not scratch.is_relative_to(workspace.root / "runtime")
    (scratch / "projectmem.sqlite3").write_bytes(b"local non-executable state")
    (scratch / "__pycache__").mkdir()
    (scratch / "__pycache__" / "server.pyc").write_bytes(b"cached bytecode")
    assert runtime_fingerprint(workspace, name) == before

    # No runtime files are ignored: source or foreign-cache injection remains
    # an immediate PermissionError even after an independent signature.
    (workspace.root / "runtime" / name / "runtime.sqlite3").write_bytes(b"unexpected")
    with pytest.raises(PermissionError, match="Unexpected runtime"):
        runtime_fingerprint(workspace, name)


def test_local_scratch_rejects_symlink_escape(tmp_path):
    from aura_core.evolution.external_staging import EvolutionWorkspace
    from aura_core.evolution.sandbox_preflight import (
        local_job_scratch_root, SandboxUntrusted,
    )

    workspace = EvolutionWorkspace(tmp_path / "evolution")
    outside = tmp_path / "outside"
    outside.mkdir()
    container = workspace.root / "runtime-work"
    container.mkdir()
    link = container / "riponcm__projectmem"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation is not supported")
    with pytest.raises(SandboxUntrusted, match="Unsafe local MCP scratch"):
        local_job_scratch_root(workspace, "riponcm__projectmem")
    assert not list(outside.iterdir())


def test_legacy_queue_null_items_are_not_starved_by_retryable_rejections(tmp_path):
    from aura_core.evolution.external_staging import EvolutionWorkspace
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    gateway = PartialGateway()
    engine = SelfDiscoveryEngine(
        gateway=gateway, workspace=workspace, auto_stage=True,
        db_path=workspace.root / "catalog" / "proposals.sqlite3",
    )
    with engine._connect() as db:
        for idx in range(52):
            db.execute(
                "INSERT INTO evolution_proposals "
                "(proposal_id,repository,url,description,license,capability_hint,"
                "created_at,package_status,package_error,stage_retry_version) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (f"failed{idx}", f"archive/reject{idx}",
                 f"https://github.com/archive/reject{idx}", "local FastMCP",
                 "MIT", "FastMCP", idx, "STAGING_REJECTED",
                 "GitHub download byte budget exceeded", 0),
            )
        db.execute(
            "INSERT INTO evolution_proposals "
            "(proposal_id,repository,url,description,license,capability_hint,created_at)"
            "VALUES (?,?,?,?,?,?,?)",
            ("queued", "riponcm/projectmem", "https://github.com/riponcm/projectmem",
             "local FastMCP", "MIT", "FastMCP", 999),
        )
    result = run(engine.run_once(multi_source=True))
    assert result["staged_count"] >= 1
    with engine._connect() as db:
        assert db.execute(
            "SELECT package_status FROM evolution_proposals WHERE proposal_id='queued'"
        ).fetchone()[0] == "READY_FOR_OWNER_REVIEW"
