from __future__ import annotations

import pytest

from aura_core.agent.runtime import ExecutionResult, Plan, PlanState, PlanStep, Task
from aura_core.kernel.permissions import RiskLevel
from aura_core.application.sandbox_contract import SandboxJob
from aura_core.application.sandbox_runner import (
    DockerPythonRunner,
    SandboxAuthorizationError,
    SandboxUnavailable,
)
from aura_core.application.autonomy_lab import run_python_draft
from aura_core.application.task_memory import TaskMemoryCoordinator
from aura_core.application.tasks import AgentTaskService, SubmittedTask
from aura_core.memory.hierarchical_memory import SQLiteEpisodicMemory


class CapturingRuntime:
    def __init__(self) -> None:
        self.task = None

    async def execute(self, task, plan):
        self.task = task
        return ExecutionResult(
            plan_id=plan.plan_id, state=PlanState.SUCCEEDED, steps=(), elapsed_seconds=0.01
        )


def test_task_memory_is_loaded_untrusted_and_checkpointed(tmp_path):
    store = SQLiteEpisodicMemory(tmp_path / "memory.sqlite3")
    store.append(
        principal_id="p1", task_id="t1", content="old observation",
        source="test", metadata={},
    )
    coordinator = TaskMemoryCoordinator(store)
    context = coordinator.begin(principal_id="p1", task_id="t1", goal="continue work")
    assert any(item.content == "old observation" and item.untrusted for item in context)
    assert all(item.untrusted for item in context)
    coordinator.finish(
        principal_id="p1", task_id="t1", state="succeeded", summary="done"
    )
    checkpoint = store.load_checkpoint(principal_id="p1", task_id="t1")
    assert checkpoint is not None
    assert checkpoint["state"] == "succeeded"
    assert store.recall(principal_id="p2", task_id="t1") == []


@pytest.mark.asyncio
async def test_task_service_attaches_scoped_memory_without_bypassing_runtime(tmp_path):
    store = SQLiteEpisodicMemory(tmp_path / "memory.sqlite3")
    coordinator = TaskMemoryCoordinator(store)
    runtime = CapturingRuntime()
    service = AgentTaskService(runtime, memory=coordinator)
    task = Task(task_id="t1", principal_id="p1", title="research", resource_scope="public-web")
    plan = Plan(
        plan_id="plan-1", task_id="t1",
        steps=(PlanStep(step_id="step-1", capability_id="cap", operation_id="op", tool_name="tool", risk_level=RiskLevel.LOW),),
    )
    result = await service.submit(SubmittedTask(task, plan))
    assert result.state is PlanState.SUCCEEDED
    assert runtime.task is not None
    assert any(item.kind == "goal" and item.untrusted for item in runtime.task.memory_context)
    assert store.load_checkpoint(principal_id="p1", task_id="t1")["state"] == "succeeded"


def _job() -> SandboxJob:
    return SandboxJob(
        job_id="job-1", principal_id="p1", runner="docker",
        source="print('hello')", input_json="{}", authorization_id="auth-1",
    )


def test_sandbox_fails_closed_without_authorizer():
    runner = DockerPythonRunner(
        image="python:3.13-slim@sha256:" + "a" * 64,
        docker_executable="/not/used",
    )
    with pytest.raises(SandboxAuthorizationError):
        runner.run(_job())


def test_sandbox_fails_closed_when_authorization_denied():
    runner = DockerPythonRunner(
        authorizer=lambda _job: False,
        image="python:3.13-slim@sha256:" + "a" * 64,
        docker_executable="/not/used",
    )
    with pytest.raises(SandboxAuthorizationError):
        run_python_draft(_job(), authorize=lambda _job: False, runner=runner)


def test_sandbox_fails_closed_without_docker(monkeypatch):
    from aura_core.application import sandbox_runner
    monkeypatch.setattr(sandbox_runner.shutil, "which", lambda _name: None)
    runner = DockerPythonRunner(
        authorizer=lambda _job: True,
        image="python:3.13-slim@sha256:" + "a" * 64,
    )
    with pytest.raises(SandboxUnavailable):
        runner.run(_job())
