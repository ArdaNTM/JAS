from __future__ import annotations

import asyncio
import json

import pytest

from aura_core.agent.runtime import PlanState
from aura_core.application.autonomous_adapters import (
    AllowedOperation, BudgetAutonomyGovernor, CapabilityDrivenPlanner,
    DockerIsolatedSandbox, SandboxLimits,
)
from aura_core.application.governed_autonomous_loop import (
    GovernedAutonomousLoop, SandboxReport, VerificationReport,
)
from aura_core.application.tasks import SubmittedTask
from aura_core.kernel.permissions import RiskLevel


class Completion:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def complete_json(self, *, system_prompt, user_prompt):
        self.calls.append((system_prompt, json.loads(user_prompt)))
        return self.response


def operation():
    return AllowedOperation(
        capability_id="filesystem.read", operation_id="read_file",
        tool_name="read_file", risk_level=RiskLevel.LOW,
        allowed_argument_keys=frozenset({"path"}),
    )


def response(**step_overrides):
    step = {
        "capability_id": "filesystem.read", "operation_id": "read_file",
        "tool_name": "read_file", "arguments": {"path": "workspace:alice/file.txt"},
        "depends_on": [],
    }
    step.update(step_overrides)
    return {"steps": [step]}


def test_capability_planner_maps_allowlisted_structured_output():
    async def scenario():
        provider = Completion(response())
        planner = CapabilityDrivenPlanner(completion_provider=provider, operations=[operation()])
        submissions = await planner.propose(
            goal="read file", principal_id="alice", resource_scope="workspace:alice",
            iteration=1, feedback=(),
        )
        assert len(submissions) == 1
        assert submissions[0].task.principal_id == "alice"
        assert submissions[0].task.resource_scope == "workspace:alice"
        assert submissions[0].plan.steps[0].tool_name == "read_file"
        assert provider.calls[0][1]["goal_untrusted"] == "read file"
    asyncio.run(scenario())


@pytest.mark.parametrize("bad", [
    {"capability_id": "shell.exec", "operation_id": "run", "tool_name": "shell"},
    {"arguments": {"path": "x", "admin": True}},
])
def test_capability_planner_rejects_unapproved_operations_or_arguments(bad):
    async def scenario():
        planner = CapabilityDrivenPlanner(
            completion_provider=Completion(response(**bad)), operations=[operation()]
        )
        with pytest.raises(ValueError):
            await planner.propose(
                goal="read file", principal_id="alice", resource_scope="workspace:alice",
                iteration=1, feedback=(),
            )
    asyncio.run(scenario())


def test_governor_fails_closed_and_enforces_per_principal_budget():
    async def scenario():
        governor = BudgetAutonomyGovernor(
            max_iterations=2, max_tasks_per_iteration=2,
            max_tasks_per_principal=2, allowed_principals=frozenset({"alice"}),
        )
        assert await governor.authorize_iteration(
            goal="work", principal_id="alice", iteration=1, task_count=0,
            retrying_after_execution=False,
        )
        assert await governor.authorize_iteration(
            goal="work", principal_id="alice", iteration=1, task_count=2,
            retrying_after_execution=False,
        )
        assert not await governor.authorize_iteration(
            goal="other", principal_id="alice", iteration=2, task_count=1,
            retrying_after_execution=False,
        )
        assert not await governor.authorize_iteration(
            goal="work", principal_id="mallory", iteration=1, task_count=0,
            retrying_after_execution=False,
        )
        assert governor.snapshot("alice")["tasks_reserved"] == 2
    asyncio.run(scenario())


def test_governor_denies_retry_after_execution_by_default():
    async def scenario():
        governor = BudgetAutonomyGovernor()
        assert not await governor.authorize_iteration(
            goal="work", principal_id="alice", iteration=2, task_count=0,
            retrying_after_execution=True,
        )
    asyncio.run(scenario())


def test_docker_sandbox_refuses_host_fallback_when_docker_missing(monkeypatch):
    import aura_core.application.autonomous_adapters as adapters

    monkeypatch.setattr(adapters.shutil, "which", lambda _: None)
    sandbox = DockerIsolatedSandbox(limits=SandboxLimits(timeout_seconds=0.2))
    with pytest.raises(RuntimeError, match="refusing host execution"):
        asyncio.run(sandbox.run_python("print('hello')", principal_id="alice"))


class Planner:
    def __init__(self, task):
        self.task = task

    async def propose(self, **kwargs):
        return (self.task,)


class Sandbox:
    async def validate(self, **kwargs):
        return SandboxReport(True, "ok")


class Verifier:
    async def verify(self, **kwargs):
        return VerificationReport(True, "ok")


class Governor:
    async def authorize_iteration(self, **kwargs):
        return True


class BlockingTaskService:
    def __init__(self):
        self.started = asyncio.Event()
        self.cancelled = False

    async def submit_chain(self, submissions):
        self.started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return ()


def test_loop_propagates_external_cancellation_during_execution():
    async def scenario():
        from aura_core.agent.runtime import Plan, PlanStep, Task
        task = Task("task-1", "alice", "work", "workspace:alice")
        plan = Plan("plan-1", "task-1", (
            PlanStep("step-1", "filesystem.read", "read_file", "read_file", RiskLevel.LOW),
        ))
        submitted = SubmittedTask(task, plan)
        service = BlockingTaskService()
        cancel_state = {"requested": False}
        loop = GovernedAutonomousLoop(
            planner=Planner(submitted), sandbox=Sandbox(), verifier=Verifier(),
            governor=Governor(), task_service=service, overall_timeout_seconds=2,
        )
        running = asyncio.create_task(loop.run(
            goal="work", principal_id="alice", resource_scope="workspace:alice",
            cancelled=lambda: cancel_state["requested"],
        ))
        await asyncio.wait_for(service.started.wait(), timeout=1)
        cancel_state["requested"] = True
        result = await asyncio.wait_for(running, timeout=1)
        assert result.status == "cancelled"
        assert service.cancelled is True
    asyncio.run(scenario())
