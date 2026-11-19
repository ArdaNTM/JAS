import asyncio
import hashlib
import time
from datetime import datetime, UTC
from types import SimpleNamespace

import pytest

from aura_core.application.subsystem_pack1 import (
    ApprovedSandboxDispatcher,
    DevelopmentProposal,
    LocalDevelopmentPlanner,
    MaintenanceAutomation,
    RemoteControlPrecondition,
)


class Telemetry:
    def __init__(self, *, status="ok"):
        self.calls = 0
        self.state = status

    def snapshot(self):
        self.calls += 1
        return {"status": self.state, "cpu_percent": 12, "memory_percent": 35, "alerts": []}


class Gateway:
    def __init__(self, decision="allow"):
        self.calls = []
        self.decision = decision

    async def invoke(self, request):
        from aura_core.kernel.permissions import AuthorizationDecision
        self.calls.append(request)
        return SimpleNamespace(decision=AuthorizationDecision(self.decision), result={"status": "completed"})


def test_maintenance_durable_single_claim(tmp_path):
    telemetry = Telemetry()
    queue = MaintenanceAutomation(tmp_path / "maintenance.sqlite", telemetry)
    queue.schedule("check-1", datetime.fromtimestamp(1000, tz=UTC))
    assert queue.run_due(now=999) == []
    assert [x["state"] for x in queue.run_due(now=1000)] == ["done"]
    assert MaintenanceAutomation(tmp_path / "maintenance.sqlite", telemetry).status("check-1")["state"] == "done"
    assert queue.run_due(now=1001) == []
    assert telemetry.calls == 1


def test_maintenance_rejects_invalid_and_non_mutating(tmp_path):
    queue = MaintenanceAutomation(tmp_path / "m.sqlite", Telemetry(status="unavailable"))
    with pytest.raises(ValueError):
        queue.schedule("../escape", datetime.now(UTC))
    with pytest.raises(ValueError):
        queue.schedule("safe", datetime.now().replace(tzinfo=None))
    queue.schedule("safe", datetime.fromtimestamp(1, tz=UTC))
    assert queue.run_due(now=2)[0]["state"] == "failed"
    with pytest.raises(ValueError):
        queue.run_due(limit=0)


def _remote(tmp_path, gateway):
    return RemoteControlPrecondition(
        gateway=gateway, db_path=tmp_path / "nonces.sqlite", device_id="pc-1",
        principal_id="local_owner", key=b"r" * 32,
    )


def _envelope():
    return {"device_id": "pc-1", "principal_id": "local_owner", "nonce": "a" * 32,
            "expires_at": int(time.time()) + 45,
            "action": {"action": "observe"}, "approval_id": None}


def test_remote_signature_nonce_and_gateway_denial(tmp_path):
    gateway = Gateway(decision="require_approval")
    remote = _remote(tmp_path, gateway)
    envelope = _envelope()
    signed = remote.fingerprint(envelope)
    response = asyncio.run(remote.forward(envelope, signed))
    assert response.decision.value == "require_approval"
    assert gateway.calls[0].capability_id == "ScreenControl"
    assert gateway.calls[0].tool_name == "screen_control"
    with pytest.raises(PermissionError, match="replayed"):
        asyncio.run(_remote(tmp_path, gateway).forward(envelope, signed))
    assert len(gateway.calls) == 1


def test_remote_rejects_tampering_without_dispatch(tmp_path):
    gateway = Gateway()
    remote = _remote(tmp_path, gateway)
    envelope = _envelope()
    signed = remote.fingerprint(envelope)
    envelope["action"] = {"action": "click", "x": 3, "y": 9}
    with pytest.raises(PermissionError, match="signature"):
        asyncio.run(remote.forward(envelope, signed))
    assert gateway.calls == []


def test_remote_rejects_stale_and_scope_injection(tmp_path):
    gateway = Gateway()
    remote = _remote(tmp_path, gateway)
    envelope = _envelope()
    envelope["expires_at"] = int(time.time()) - 1
    with pytest.raises(PermissionError, match="expired"):
        asyncio.run(remote.forward(envelope, remote.fingerprint(envelope)))
    envelope = _envelope()
    envelope["resource_scope"] = "all"
    with pytest.raises(PermissionError, match="schema"):
        asyncio.run(remote.forward(envelope, remote.fingerprint(envelope)))
    assert gateway.calls == []


def test_remote_requires_strong_peer_key(tmp_path):
    with pytest.raises(ValueError, match="32 bytes"):
        RemoteControlPrecondition(gateway=Gateway(), db_path=tmp_path / "n.sqlite",
                                  device_id="pc", principal_id="local_owner", key=b"weak")


def test_planner_parses_real_inference_result_without_execution():
    class Response:
        async def complete_json(self, **kwargs):
            assert "No tools" in kwargs["system_prompt"]
            return {"source": "def add(x,y): return x+y", "tests": "assert add(1,2)==3"}
    proposal = asyncio.run(LocalDevelopmentPlanner(Response()).propose("Add two numbers"))
    assert proposal.digest == hashlib.sha256((proposal.source + "\0" + proposal.tests).encode()).hexdigest()


def test_planner_rejects_invalid_code():
    class Response:
        async def complete_json(self, **kwargs):
            return {"source": "def broken(", "tests": "assert True"}
    with pytest.raises(SyntaxError):
        asyncio.run(LocalDevelopmentPlanner(Response()).propose("Fix syntax"))


def test_sandbox_dispatch_requires_gateway_allow():
    gateway = Gateway(decision="deny")
    dispatcher = ApprovedSandboxDispatcher(gateway, principal_id="local_owner")
    source, tests = "x=1", "assert x==1"
    proposal = DevelopmentProposal(source, tests, hashlib.sha256((source + "\0" + tests).encode()).hexdigest())
    with pytest.raises(PermissionError, match="Gateway"):
        asyncio.run(dispatcher.execute(job_id="job-1", proposal=proposal, approval_id=None))
    assert gateway.calls[0].tool_name == "codeact_execute"
    assert gateway.calls[0].capability_id == "sandbox.codeact.execute"


def test_sandbox_does_not_execute_locally_and_checks_digest():
    gateway = Gateway()
    dispatcher = ApprovedSandboxDispatcher(gateway, principal_id="local_owner")
    proposal = DevelopmentProposal("raise RuntimeError('untrusted')", "assert True", "0" * 64)
    with pytest.raises(ValueError, match="digest"):
        asyncio.run(dispatcher.execute(job_id="job-1", proposal=proposal, approval_id=None))
    assert gateway.calls == []
