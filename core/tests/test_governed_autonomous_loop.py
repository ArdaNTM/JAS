from __future__ import annotations

import asyncio

from aura_core.agent.runtime import ExecutionResult, Plan, PlanState, PlanStep, Task
from aura_core.application.governed_autonomous_loop import (
    GovernedAutonomousLoop, SandboxReport, VerificationReport,
)
from aura_core.application.tasks import SubmittedTask
from aura_core.kernel.events import EventBus
from aura_core.kernel.permissions import RiskLevel


def submission(task_id: str = "task-1") -> SubmittedTask:
    task = Task(task_id, "alice", "do bounded work", "workspace:alice")
    plan = Plan(f"plan-{task_id}", task_id, (
        PlanStep("step-1", "capability.read", "read", "read_file", RiskLevel.LOW),
    ))
    return SubmittedTask(task, plan)


class Planner:
    def __init__(self, proposals):
        self.proposals = proposals
        self.calls = []

    async def propose(self, **kwargs):
        self.calls.append(kwargs)
        return self.proposals[min(len(self.calls) - 1, len(self.proposals) - 1)]


class Sandbox:
    def __init__(self, reports):
        self.reports = reports
        self.calls = 0

    async def validate(self, **kwargs):
        report = self.reports[min(self.calls, len(self.reports) - 1)]
        self.calls += 1
        return report


class Verifier:
    def __init__(self, report):
        self.report = report
        self.calls = 0

    async def verify(self, **kwargs):
        self.calls += 1
        return self.report


class Governor:
    def __init__(self, decisions=(True, True)):
        self.decisions = decisions
        self.calls = []

    async def authorize_iteration(self, **kwargs):
        self.calls.append(kwargs)
        return self.decisions[min(len(self.calls) - 1, len(self.decisions) - 1)]


class TaskService:
    def __init__(self):
        self.calls = []

    async def submit_chain(self, submissions):
        self.calls.append(tuple(submissions))
        return tuple(
            ExecutionResult(item.plan.plan_id, PlanState.SUCCEEDED, (), 0.01)
            for item in submissions
        )


def test_governed_loop_plans_sandbox_executes_and_verifies():
    async def scenario():
        bus = EventBus()
        planner = Planner([[submission()]])
        sandbox = Sandbox([SandboxReport(True, "plan is bounded")])
        verifier = Verifier(VerificationReport(True, "goal met"))
        governor = Governor()
        service = TaskService()
        loop = GovernedAutonomousLoop(
            planner=planner, sandbox=sandbox, verifier=verifier,
            governor=governor, task_service=service, event_bus=bus,
        )
        result = await loop.run(
            goal="read a file safely", principal_id="alice", resource_scope="workspace:alice"
        )
        assert result.status == "succeeded"
        assert result.execution_started is True
        assert len(service.calls) == 1
        assert len(governor.calls) == 2  # preflight and pre-execution policy checks
        assert bus.snapshot()["published_total"] >= 4
    asyncio.run(scenario())


def test_sandbox_rejection_reflexes_and_replans_without_execution():
    async def scenario():
        first = submission("draft-1")
        second = submission("draft-2")
        planner = Planner([[first], [second]])
        sandbox = Sandbox([
            SandboxReport(False, "unsafe proposal", ("scope too broad",)),
            SandboxReport(True, "revised proposal accepted"),
        ])
        verifier = Verifier(VerificationReport(True, "goal met"))
        service = TaskService()
        loop = GovernedAutonomousLoop(
            planner=planner, sandbox=sandbox, verifier=verifier,
            governor=Governor((True, True, True, True)), task_service=service,
            max_iterations=2,
        )
        result = await loop.run(
            goal="read a file", principal_id="alice", resource_scope="workspace:alice"
        )
        assert result.status == "succeeded"
        assert result.iterations == 2
        assert len(planner.calls) == 2
        assert len(service.calls) == 1
        assert planner.calls[1]["feedback"] == ("scope too broad",)
    asyncio.run(scenario())


def test_governor_denial_fails_closed_before_execution():
    async def scenario():
        service = TaskService()
        loop = GovernedAutonomousLoop(
            planner=Planner([[submission()]]),
            sandbox=Sandbox([SandboxReport(True, "safe")]),
            verifier=Verifier(VerificationReport(True, "ok")),
            governor=Governor((False,)), task_service=service,
        )
        result = await loop.run(
            goal="do work", principal_id="alice", resource_scope="workspace:alice"
        )
        assert result.status == "denied"
        assert result.execution_started is False
        assert service.calls == []
    asyncio.run(scenario())


def test_verification_failure_does_not_replay_side_effects_by_default():
    async def scenario():
        service = TaskService()
        verifier = Verifier(VerificationReport(False, "not verified", ("missing evidence",)))
        loop = GovernedAutonomousLoop(
            planner=Planner([[submission()]]),
            sandbox=Sandbox([SandboxReport(True, "safe")]),
            verifier=verifier, governor=Governor(), task_service=service,
        )
        result = await loop.run(
            goal="change a file", principal_id="alice", resource_scope="workspace:alice"
        )
        assert result.status == "needs_review"
        assert result.execution_started is True
        assert len(service.calls) == 1
        assert result.feedback == ("missing evidence",)
    asyncio.run(scenario())


def test_cross_principal_or_resource_scope_proposals_are_rejected():
    async def scenario():
        bad = submission()
        other_task = Task("task-1", "bob", "other", "workspace:alice")
        bad = SubmittedTask(other_task, bad.plan)
        service = TaskService()
        loop = GovernedAutonomousLoop(
            planner=Planner([[bad]]),
            sandbox=Sandbox([SandboxReport(True, "safe")]),
            verifier=Verifier(VerificationReport(True, "ok")),
            governor=Governor(), task_service=service,
        )
        result = await loop.run(
            goal="do work", principal_id="alice", resource_scope="workspace:alice"
        )
        assert result.status == "rejected"
        assert service.calls == []
    asyncio.run(scenario())
