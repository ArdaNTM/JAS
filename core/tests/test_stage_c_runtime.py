from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from aura_core.agent.runtime import Plan, PlanStep, Task
from aura_core.application.tasks import SubmittedTask
from aura_core.application.stage_c_runtime import (
    MAX_ACTIONS, StageCLedger, StageCController, StageCError,
)
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.mcp.dispatch_context import DispatchGrant, enter_dispatch, leave_dispatch
from aura_core.mcp.stage_c_browser import BrowserControlMCPProvider, OriginGuard, safe_origin


@pytest.fixture
def ledger(owner_private_dir: Path) -> StageCLedger:
    return StageCLedger(owner_private_dir / "stage-c.sqlite3")


class Planner:
    def __init__(self, count: int = 1, capability: str = "BrowserControl"):
        self.count, self.capability, self.calls = count, capability, 0

    async def propose(self, *, goal, principal_id, resource_scope, **kwargs):
        self.calls += 1
        step = "browser_action" if self.capability == "BrowserControl" else "screen_control"
        args = {"action": "read"} if self.capability == "BrowserControl" else {"action": "key", "key": "escape"}
        task = Task("task-test", principal_id, goal, resource_scope, max_steps=MAX_ACTIONS)
        plan = Plan("plan-test", task.task_id, tuple(
            PlanStep(f"step-{i}", self.capability, self.capability, step,
                     RiskLevel.HIGH, arguments=args, max_attempts=1)
            for i in range(self.count)
        ))
        return (SubmittedTask(task, plan),)


class Gateway:
    def __init__(self, *, pending=False):
        self.pending, self.calls = pending, []

    async def invoke(self, request):
        self.calls.append(request)
        if self.pending and request.approval_id is None:
            return SimpleNamespace(
                decision=AuthorizationDecision.REQUIRE_APPROVAL,
                approval_id="approval-1", result=None,
            )
        return SimpleNamespace(
            decision=AuthorizationDecision.ALLOW, approval_id=request.approval_id,
            result={"untrusted": True, "text": "untrusted web page data"},
        )


def test_plan_gateway_and_budget_are_persistent(ledger):
    async def run():
        planner, gateway = Planner(count=2), Gateway()
        driver = StageCController(ledger=ledger, gateway=gateway, planner=planner)
        run_id = ledger.create("alice", "Read public page", "local_default")
        await driver.execute_until_pause(run_id, "alice")
        state = ledger.get(run_id, "alice")
        assert state["state"] == "succeeded"
        assert state["used"] == 2 and state["cursor"] == 2
        assert planner.calls == 1 and len(gateway.calls) == 2
        assert gateway.calls[0].arguments["run_id"] == run_id
        assert all(c.capability_id == "BrowserControl" for c in gateway.calls)
        with pytest.raises(StageCError):
            ledger.reserve(run_id, "alice")
        with pytest.raises(KeyError):
            ledger.get(run_id, "mallory")
    asyncio.run(run())


def test_consumed_approval_is_resumed_exactly_once(ledger):
    async def run():
        gateway = Gateway(pending=True)
        planner = Planner()
        driver = StageCController(ledger=ledger, gateway=gateway, planner=planner)
        run_id = ledger.create("alice", "Read public page", "local_default")
        await driver.execute_until_pause(run_id, "alice")
        assert ledger.public(run_id, "alice")["state"] == "awaiting_approval"
        assert ledger.public(run_id, "alice")["used"] == 1
        first_key = gateway.calls[0].request_id
        await driver.execute_until_pause(run_id, "alice", resume=True)
        assert ledger.public(run_id, "alice")["state"] == "succeeded"
        assert ledger.public(run_id, "alice")["used"] == 1
        assert gateway.calls[1].approval_id == "approval-1"
        assert gateway.calls[1].request_id == first_key
        with pytest.raises(StageCError):
            ledger.reserve(run_id, "alice", resume=True)
    asyncio.run(run())


def test_unknown_outcome_never_replays_after_restart(ledger):
    run_id = ledger.create("alice", "Read public page", "local_default")
    ledger.set_plan(run_id, "alice", [{
        "capability": "BrowserControl", "operation": "BrowserControl",
        "tool": "browser_action", "arguments": {"action": "read", "run_id": run_id},
    }])
    step, key, approval = ledger.reserve(run_id, "alice")
    assert step["arguments"]["run_id"] == run_id
    assert ledger.get(run_id, "alice")["state"] == "in_flight"
    # A new process/controller sees the persisted in-flight state and does NOT
    # treat the action as safe to retry.
    new_ledger = StageCLedger(Path(ledger._db.execute("PRAGMA database_list").fetchone()[2]))
    assert new_ledger.get(run_id, "alice")["state"] == "in_flight"
    with pytest.raises(StageCError):
        new_ledger.reserve(run_id, "alice")
    new_ledger.mark_unknown(run_id, "alice")
    assert new_ledger.get(run_id, "alice")["state"] == "needs_review"


def test_kill_persists_and_denies_future_runs(ledger):
    async def run():
        driver = StageCController(ledger=ledger, gateway=Gateway(), planner=Planner())
        run_id = ledger.create("alice", "Read public page", "local_default")
        await driver.kill()
        assert ledger.stopped() is True
        assert ledger.public(run_id, "alice")["state"] == "stopped"
        with pytest.raises(StageCError, match="kill switch"):
            ledger.create("alice", "new run", "local_default")
        await driver.execute_until_pause(run_id, "alice")
        assert ledger.public(run_id, "alice")["used"] == 0
    asyncio.run(run())


def test_budget_rejects_ninth_step_without_gateway_dispatch(ledger):
    async def run():
        controller = StageCController(ledger=ledger, gateway=Gateway(), planner=Planner(count=9))
        run_id = ledger.create("alice", "Read public page", "local_default")
        with pytest.raises(StageCError):
            await controller.execute_until_pause(run_id, "alice")
    asyncio.run(run())


@pytest.mark.parametrize("url", [
    "http://example.org/", "https://127.0.0.1/", "https://localhost/",
    "https://example.org:8443/", "https://user@example.org/",
    "https://localhost.localdomain/", "https://example.org.internal/",
    "file:///etc/passwd", "https://example.org.local/", "javascript:alert(1)",
])
def test_browser_rejects_unsafe_origin(url):
    with pytest.raises(ValueError):
        safe_origin(url)


class FakeSessions:
    def __init__(self):
        self.calls = []
    async def perform(self, run_id, action, args):
        self.calls.append((run_id, action))
        return {"executed": True}


def test_browser_provider_needs_consumed_gateway_grant():
    async def run():
        sessions = FakeSessions()
        provider = BrowserControlMCPProvider(sessions)
        args = {"run_id": "00000000-0000-0000-0000-000000000001", "action": "read"}
        with pytest.raises(PermissionError):
            await provider.call_tool("browser_action", args)
        grant = enter_dispatch(DispatchGrant(
            "alice", "BrowserControl", "browser_action", False, "high",
        ))
        try:
            with pytest.raises(PermissionError):
                await provider.call_tool("browser_action", args)
        finally:
            leave_dispatch(grant)
        grant = enter_dispatch(DispatchGrant(
            "alice", "BrowserControl", "browser_action", True, "high",
        ))
        try:
            assert (await provider.call_tool("browser_action", args))["executed"]
        finally:
            leave_dispatch(grant)
        assert len(sessions.calls) == 1
    asyncio.run(run())


def test_exact_origin_allowlist_never_accepts_subdomains():
    guard = OriginGuard(("https://example.org",))
    assert guard.origins == frozenset({"https://example.org"})
    with pytest.raises(ValueError):
        OriginGuard(("https://example.org/path",))

def test_planner_failure_is_quarantined_not_replanned(ledger):
    class BrokenPlanner:
        calls = 0
        async def propose(self, **_):
            self.calls += 1
            raise RuntimeError("invalid model response")
    async def run():
        planner = BrokenPlanner()
        controller = StageCController(ledger=ledger, gateway=Gateway(), planner=planner)
        run_id = ledger.create("alice", "read page", "local_default")
        with pytest.raises(RuntimeError):
            await controller.execute_until_pause(run_id, "alice")
        assert ledger.public(run_id, "alice")["state"] == "needs_review"
        await controller.execute_until_pause(run_id, "alice")
        assert planner.calls == 1
    asyncio.run(run())
