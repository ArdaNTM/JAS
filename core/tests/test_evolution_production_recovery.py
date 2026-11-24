"""Live Windows recovery: transient failures never bypass delegated activation."""
from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from aura_core.evolution import attestor_worker, windows_owner_storage
from aura_core.evolution.activation_runtime import DelegatedMCPActivationManager
from aura_core.evolution.external_staging import EvolutionWorkspace, CAPABILITY
from aura_core.evolution.self_discovery import SelfDiscoveryEngine
from aura_core.kernel.permissions import AuthorizationDecision

from test_evolution_autonomous_activation import FakeProvider, _kernel, _signed_fixture


def test_owner_acl_timeout_fails_closed_with_45_second_budget(tmp_path, monkeypatch):
    executable = tmp_path / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    (executable.parent / "Modules").mkdir()
    monkeypatch.setattr(windows_owner_storage, "os", SimpleNamespace(
        name="nt", environ={"SystemRoot": str(tmp_path)},
    ))

    def timeout(command, **kwargs):
        assert kwargs["timeout"] == 45
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(windows_owner_storage.subprocess, "run", timeout)
    with pytest.raises(PermissionError, match="Windows owner ACL verification timed out"):
        windows_owner_storage._powershell("Get-Acl", path=tmp_path)


def test_watch_survives_timeout_and_io_error(tmp_path, monkeypatch, capsys):
    calls = []
    sleeps = []

    class Worker:
        async def scan(self):
            calls.append(1)
            if len(calls) == 1:
                raise subprocess.TimeoutExpired(["secret-command"], 15)
            if len(calls) == 2:
                raise OSError("transient I/O")
            return [{"repository": "sample/mcp"}]

    monkeypatch.setattr(attestor_worker, "EvolutionWorkspace", lambda root: object())
    monkeypatch.setattr(attestor_worker, "_load_signer", lambda path: object())
    monkeypatch.setattr(attestor_worker, "IndependentMCPAttestorWorker", lambda **kw: Worker())
    monkeypatch.setattr(sys, "argv", [
        "attestor_worker", "--evolution-root", str(tmp_path), "--private-key",
        str(tmp_path / "key.pem"), "--watch", "--poll-seconds", "30",
    ])

    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 3:
            raise KeyboardInterrupt

    monkeypatch.setattr(attestor_worker.time, "sleep", sleep)
    with pytest.raises(KeyboardInterrupt):
        attestor_worker.main()
    captured = capsys.readouterr()
    assert len(calls) == 3 and sleeps == [30, 30, 30]
    assert "TimeoutExpired" in captured.err and "OSError" in captured.err
    assert "secret-command" not in captured.err
    assert json.loads(captured.out)["attested_packages"] == 1


def test_one_shot_attestor_still_raises(tmp_path, monkeypatch):
    class Worker:
        async def scan(self):
            raise PermissionError("owner unavailable")

    monkeypatch.setattr(attestor_worker, "EvolutionWorkspace", lambda root: object())
    monkeypatch.setattr(attestor_worker, "_load_signer", lambda path: object())
    monkeypatch.setattr(attestor_worker, "IndependentMCPAttestorWorker", lambda **kw: Worker())
    monkeypatch.setattr(sys, "argv", [
        "attestor_worker", "--evolution-root", str(tmp_path), "--private-key",
        str(tmp_path / "key.pem"),
    ])
    with pytest.raises(PermissionError):
        attestor_worker.main()


def test_signed_candidate_beyond_old_100_item_cutoff_activates(tmp_path, monkeypatch):
    workspace, name, repo = _signed_fixture(tmp_path, monkeypatch)
    workspace.max_items = 125
    # These earlier directories are inert invalid candidates, not signed evidence.
    for index in range(101):
        (workspace.root / "verified" / f"aa{index:03}__pending").mkdir()
    kernel, _ = _kernel()
    async def factory(*args):
        return FakeProvider()
    manager = DelegatedMCPActivationManager(
        workspace=workspace, kernel=kernel, provider_factory=factory,
    )
    manager._persist(repo, "WAITING_ATTESTATION",
                     reason_code="INDEPENDENT_ATTESTATION_MISSING")
    async def scenario():
        assert await manager.scan(limit=1) == [repo]
        row = next(r for r in manager._load_inventory()["active"] if r["repository"] == repo)
        assert row["status"] == "ACTIVE"
        await manager.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("cause", ["static_evidence", "category", "oversized"])
def test_present_attestation_never_leaves_stale_missing_reason(tmp_path, monkeypatch, cause):
    workspace, name, repo = _signed_fixture(tmp_path, monkeypatch)
    kernel, _ = _kernel()
    async def factory(*args):
        return FakeProvider()
    manager = DelegatedMCPActivationManager(
        workspace=workspace, kernel=kernel, provider_factory=factory,
    )
    package = workspace.root / "verified" / name
    async def scenario():
        target_repo = repo
        if cause == "static_evidence":
            (package / "source.zip").unlink()
            expected = "REJECTED_EVIDENCE"
        elif cause == "oversized":
            (package / "independent-attestations.json").write_bytes(b"x" * 262145)
            expected = "PermissionError"
        else:
            assert await manager.scan(limit=1) == [repo]
            target_repo = "zz/local-memory"
            other = workspace.root / "verified" / "zz__local-memory"
            shutil.copytree(package, other)
            manifest = other / "aura-capability-manifest.json"
            data = json.loads(manifest.read_text("utf-8"))
            data["repository"] = target_repo
            manifest.write_text(json.dumps(data), encoding="utf-8")
            shutil.copytree(workspace.root / "runtime" / name,
                            workspace.root / "runtime" / "zz__local-memory")
            expected = "CATEGORY_ALREADY_ACTIVE"
        manager._persist(target_repo, "WAITING_ATTESTATION",
                         reason_code="INDEPENDENT_ATTESTATION_MISSING")
        assert await manager.scan(limit=1) == []
        row = next(r for r in manager._load_inventory()["active"] if r["repository"] == target_repo)
        assert row["reason_code"] == expected
        assert row["reason_detail"]
        assert row["status"] != "ACTIVE"
        if cause == "oversized":
            assert "size budget" in row["reason_detail"]
        audit = [json.loads(line) for line in
                 (workspace.root / "logs" / "autonomous-activations.jsonl").read_text().splitlines()]
        assert any(r["repository"] == target_repo and r.get("reason_code") == expected
                   and r.get("reason_detail") for r in audit)
        await manager.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("reason", ["TimeoutError", "GitHub archive network request failed"])
@pytest.mark.parametrize("recover", [True, False])
def test_transient_staging_retries_are_bounded_and_gateway_governed(tmp_path, reason, recover):
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    repo = "sample/local-mcp"
    calls = []

    class Gateway:
        async def invoke(self, request):
            calls.append(request)
            assert request.capability_id == CAPABILITY
            if not recover or len(calls) == 1:
                if reason == "TimeoutError":
                    raise TimeoutError()
                raise ValueError(reason)
            archive = workspace.root / "verified" / "sample__local-mcp" / "source.zip"
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_bytes(b"inert static fixture")
            return SimpleNamespace(decision=AuthorizationDecision.ALLOW, result={
                "repository": repo, "status": "READY_FOR_OWNER_REVIEW",
                "source_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "sandbox_attested": False, "activation_performed": False,
                "execution_allowed": False,
            })

    engine = SelfDiscoveryEngine(gateway=Gateway(), db_path=workspace.root / "catalog" / "p.sqlite3",
                                 workspace=workspace, auto_stage=True)
    with sqlite3.connect(engine._db_path) as db:
        db.execute(
            "INSERT INTO evolution_proposals "
            "(proposal_id,repository,url,description,license,capability_hint,created_at,"
            "package_status,package_error,stage_retry_version) VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("legacy", repo, "https://github.com/" + repo, "local MCP", "MIT", "MCP",
             1, "STAGING_REJECTED", reason, 2),
        )
    first = asyncio.run(engine._stage_pending())
    assert first["attempted"] == 1 and first["rejected"][0]["reason"] == reason
    second = asyncio.run(engine._stage_pending())
    assert second["attempted"] == 1
    assert asyncio.run(engine._stage_pending())["attempted"] == 0
    assert len(calls) == 2
    assert engine.proposals()[0]["package_status"] == (
        "READY_FOR_OWNER_REVIEW" if recover else "STAGING_REJECTED")
    assert json.loads(workspace.active.read_text())["active"] == []
