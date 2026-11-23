"""Signed MCP readiness priority and bounded continuous queue regressions.

Only the package transport and public catalog are simulated. Owner delegation,
Ed25519 attestation, runtime fingerprint and MCPGateway policy are still real.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from types import SimpleNamespace

from aura_core.evolution.activation_runtime import DelegatedMCPActivationManager
from aura_core.evolution.continuous_evolution import ContinuousEvolutionController
from aura_core.evolution.external_staging import EvolutionWorkspace, CAPABILITY as STAGE_CAPABILITY
from aura_core.evolution.self_discovery import (
    CAPABILITY_ID, CATALOG_CAPABILITY, SelfDiscoveryEngine,
)
from aura_core.kernel.permissions import AuthorizationDecision
from test_evolution_autonomous_activation import (
    FakeProvider, _kernel, _signed_fixture, _request,
)


def run(coroutine):
    return asyncio.run(coroutine)


def test_ready_signed_fifth_candidate_activates_despite_four_unprepared(
    tmp_path, monkeypatch,
):
    workspace, ready_name, ready_repo = _signed_fixture(tmp_path, monkeypatch)
    source = workspace.root / "verified" / ready_name
    unready = []
    for index in range(4):
        name = f"aa{index}__pending"
        repo = f"aa{index}/pending"
        target = workspace.root / "verified" / name
        shutil.copytree(source, target)
        manifest = target / "aura-capability-manifest.json"
        data = json.loads(manifest.read_text("utf-8"))
        data["repository"] = repo
        manifest.write_text(json.dumps(data), encoding="utf-8")
        # Keep one independently quarantined and three without preparation.
        if index == 0:
            (target / "local-windows-quarantined.json").write_text(
                '{"status":"QUARANTINED","reason_code":"MCPError"}',
                encoding="utf-8",
            )
        (target / "independent-attestations.json").unlink()
        unready.append(repo)

    kernel, gateway = _kernel()
    provider = FakeProvider()
    async def factory(*_):
        return provider
    manager = DelegatedMCPActivationManager(
        workspace=workspace, kernel=kernel, provider_factory=factory,
    )

    # The candidate that sorts FIFTH alphabetically is the ONLY ready one.
    assert [x.repository for x in manager.decisions.evaluate_pending(limit=100)][-1] == ready_repo
    async def scenario():
        assert await manager.scan(limit=1) == [ready_repo]
        rows = {row["repository"]: row
                for row in json.loads(workspace.active.read_text("utf-8"))["active"]}
        assert rows[unready[0]]["status"] == "QUARANTINED"
        assert rows[unready[0]]["reason_code"] == "INDEPENDENT_ATTESTOR_QUARANTINE"
        for repo in unready[1:]:
            assert rows[repo]["status"] == "WAITING_ATTESTATION"
            assert rows[repo]["reason_code"] == "INDEPENDENT_ATTESTATION_MISSING"
        assert rows[ready_repo]["status"] == "ACTIVE"
        capability = rows[ready_repo]["capabilities"][0]
        scope = "evolution:isolated:" + rows[ready_repo]["source_sha256"] + ":lookup_local"
        allowed = await gateway.invoke(_request(capability, "lookup_local", scope))
        assert allowed.decision is AuthorizationDecision.ALLOW
        denied = await gateway.invoke(_request(capability, "lookup_local", scope,
                                              principal="unknown"))
        assert denied.decision is AuthorizationDecision.DENY
        assert provider.calls == 1
        assert await manager.scan(limit=1) == []
        await manager.close()

    run(scenario())


def test_attestor_quarantine_takes_precedence_over_missing_runtime_and_bundle(
    tmp_path, monkeypatch,
):
    workspace, name, _ = _signed_fixture(tmp_path, monkeypatch)
    shutil.rmtree(workspace.root / "runtime" / name)
    (workspace.root / "verified" / name / "independent-attestations.json").unlink()
    (workspace.root / "verified" / name / "local-windows-quarantined.json").write_text(
        '{"status":"QUARANTINED"}', encoding="utf-8",
    )
    kernel, _ = _kernel()
    manager = DelegatedMCPActivationManager(workspace=workspace, kernel=kernel)
    grant = manager.delegation.verified_grant()
    assert grant is not None

    async def scenario():
        try:
            await manager._verify_and_connect(name, grant)
        except PermissionError as exc:
            assert str(exc) == "Local Windows MCP candidate quarantined by independent attestor"
        else:
            raise AssertionError("Independent quarantine was not enforced")

        assert await manager.scan(limit=1) == []
        row = json.loads(workspace.active.read_text("utf-8"))["active"][0]
        assert row["status"] == "QUARANTINED"
        assert row["reason_code"] == "INDEPENDENT_ATTESTOR_QUARANTINE"

    run(scenario())


class BoundedGateway:
    def __init__(self, workspace):
        self.calls = []
        self.workspace = workspace
    async def invoke(self, request):
        self.calls.append(request)
        if request.capability_id in (CAPABILITY_ID, CATALOG_CAPABILITY):
            return SimpleNamespace(decision=AuthorizationDecision.ALLOW, result={"items": []})
        assert request.capability_id == STAGE_CAPABILITY
        repo = request.arguments["repository"]
        archive = (self.workspace.root / "verified" /
                   repo.replace("/", "__") / "source.zip")
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"inert gateway fixture")
        return SimpleNamespace(decision=AuthorizationDecision.ALLOW, result={
            "repository": repo,
            "status": "READY_FOR_OWNER_REVIEW",
            "source_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "sandbox_attested": False,
            "activation_performed": False, "execution_allowed": False,
        })


def test_continuous_full_multisource_drains_six_legacy_nulls_per_cycle(tmp_path):
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    gateway = BoundedGateway(workspace)
    engine = SelfDiscoveryEngine(
        gateway=gateway, db_path=workspace.root / "catalog" / "proposals.sqlite3",
        workspace=workspace, auto_stage=True,
    )
    with engine._connect() as db:
        for index in range(8):
            repo = f"legacy/memory{index}"
            db.execute(
                "INSERT INTO evolution_proposals "
                "(proposal_id,repository,url,description,license,capability_hint,created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (f"legacy{index}", repo, "https://github.com/" + repo,
                 "Local Python FastMCP sqlite, no API keys", "MIT", "FastMCP", index),
            )
    ticks = []
    first = run(engine.run_once(full_scan=True, multi_source=True, on_progress=ticks.append))
    stage_calls = [c for c in gateway.calls if c.capability_id == STAGE_CAPABILITY]
    assert first["staged_count"] == first["staging_attempted"] == 6
    assert len(stage_calls) == 6
    assert ticks == [1] * 6  # source results were empty; each stage reports immediately
    with engine._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM evolution_proposals "
                          "WHERE package_status IS NULL").fetchone()[0] == 2
    assert engine.queued_count() == 2
    second = run(engine.run_once(full_scan=True, multi_source=True))
    assert second["staged_count"] == 2
    assert engine.queued_count() == 0
    assert engine.static_ready_count() == 8


def test_continuous_hud_counter_updates_before_cycle_finishes():
    async def scenario():
        checkpoint = asyncio.Event()
        proceed = asyncio.Event()
        class Discovery:
            workspace = None
            async def run_once(self, *, full_scan, multi_source, on_progress):
                on_progress(2)
                checkpoint.set()
                await proceed.wait()
                on_progress(3)
                return {"items": [], "new_count": 5, "staged_count": 0,
                        "failed_queries": []}
            def status(self):
                return {"proposal_count": 5, "verified_static_count": 0}
            def queued_count(self):
                return 0
        controller = ContinuousEvolutionController(
            discovery=Discovery(), interval_seconds=180,
        )
        controller.start()
        await asyncio.wait_for(checkpoint.wait(), timeout=1)
        assert controller.status()["scanned_candidates"] == 2
        proceed.set()
        # Allow the scanner to publish its second incremental update.
        for _ in range(10):
            if controller.status()["scanned_candidates"] == 5:
                break
            await asyncio.sleep(0)
        assert controller.status()["scanned_candidates"] == 5
        await asyncio.wait_for(controller.stop(), timeout=1)
        assert controller.status()["scanned_candidates"] == 5

    run(scenario())
