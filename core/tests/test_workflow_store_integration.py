from __future__ import annotations

import asyncio

import pytest

from aura_core.agent.runtime import ExecutionResult, Plan, PlanState, PlanStep, StepResult, StepState, Task
from aura_core.application.tasks import AgentTaskService, SubmittedTask
from aura_core.application.task_state_machine import TaskState, TaskStateMachine
from aura_core.enterprise.workflow_store import SQLiteWorkflowStore, WorkflowStatus
from aura_core.kernel.permissions import RiskLevel


class SuccessfulRuntime:
    async def execute(self, task, plan, cancelled=None):
        return ExecutionResult(
            plan_id=plan.plan_id,
            state=PlanState.SUCCEEDED,
            steps=(StepResult("step-1", StepState.SUCCEEDED, 1, result={"ok": True}),),
            elapsed_seconds=0.01,
        )


class FailingRuntime:
    async def execute(self, task, plan, cancelled=None):
        raise RuntimeError("simulated runtime failure")


def make_submission(task_id: str = "task-workflow-1") -> SubmittedTask:
    task = Task(task_id, "local-user", "workflow integration", "local_default")
    plan = Plan(task_id + "-plan", task_id, (
        PlanStep("step-1", "test.capability", "test.operation", "test_tool", RiskLevel.LOW),
    ))
    return SubmittedTask(task=task, plan=plan)


def test_task_service_persists_workflow_lifecycle(tmp_path):
    state_machine = TaskStateMachine(str(tmp_path / "tasks.sqlite3"))
    store = SQLiteWorkflowStore(str(tmp_path / "workflows.sqlite3"))
    service = AgentTaskService(
        SuccessfulRuntime(), state_machine=state_machine, workflow_store=store
    )

    result = asyncio.run(service.submit(make_submission()))

    record = store.get("task-workflow-1")
    assert result.state is PlanState.SUCCEEDED
    assert record is not None
    assert record.status is WorkflowStatus.SUCCEEDED
    assert record.version == 3
    assert record.principal_id == "local-user"
    assert record.task_id == "task-workflow-1"

    store.close()
    state_machine.close()


def test_task_service_marks_workflow_failed_when_runtime_raises(tmp_path):
    state_machine = TaskStateMachine(str(tmp_path / "tasks.sqlite3"))
    store = SQLiteWorkflowStore(str(tmp_path / "workflows.sqlite3"))
    service = AgentTaskService(
        FailingRuntime(), state_machine=state_machine, workflow_store=store
    )

    try:
        asyncio.run(service.submit(make_submission("task-workflow-failed")))
    except RuntimeError as exc:
        assert str(exc) == "simulated runtime failure"
    else:
        raise AssertionError("runtime exception should propagate")

    record = store.get("task-workflow-failed")
    assert record is not None
    assert record.status is WorkflowStatus.FAILED
    assert record.failure_code == "runtime_RuntimeError"

    store.close()
    state_machine.close()



def test_reconcile_repairs_terminal_task_with_pending_workflow(tmp_path):
    state_machine = TaskStateMachine(str(tmp_path / "tasks.sqlite3"))
    store = SQLiteWorkflowStore(str(tmp_path / "workflows.sqlite3"))
    state_machine.create_task(
        principal_id="local-user", task_id="task-reconcile-success", goal="recover"
    )
    state_machine.transition(
        "task-reconcile-success", principal_id="local-user", target=TaskState.RUNNING
    )
    state_machine.transition(
        "task-reconcile-success", principal_id="local-user", target=TaskState.SUCCEEDED,
        result_summary="completed before workflow metadata was persisted",
    )
    store.create(
        workflow_id="task-reconcile-success",
        idempotency_key="task-reconcile-success",
        principal_id="local-user",
        task_id="task-reconcile-success",
    )
    service = AgentTaskService(
        SuccessfulRuntime(), state_machine=state_machine, workflow_store=store
    )

    reconciled = service.reconcile_workflow(
        "task-reconcile-success", principal_id="local-user"
    )

    assert reconciled.status is WorkflowStatus.SUCCEEDED
    assert reconciled.version == 3
    assert service.reconcile_workflow(
        "task-reconcile-success", principal_id="local-user"
    ) == reconciled

    store.close()
    state_machine.close()


def test_reconcile_refuses_to_overwrite_terminal_workflow_conflict(tmp_path):
    state_machine = TaskStateMachine(str(tmp_path / "tasks.sqlite3"))
    store = SQLiteWorkflowStore(str(tmp_path / "workflows.sqlite3"))
    state_machine.create_task(
        principal_id="local-user", task_id="task-reconcile-conflict", goal="recover"
    )
    state_machine.transition(
        "task-reconcile-conflict", principal_id="local-user", target=TaskState.RUNNING
    )
    store.create(
        workflow_id="task-reconcile-conflict",
        idempotency_key="task-reconcile-conflict",
        principal_id="local-user",
        task_id="task-reconcile-conflict",
    )
    store.transition(
        "task-reconcile-conflict", expected_version=1, target=WorkflowStatus.RUNNING
    )
    store.transition(
        "task-reconcile-conflict", expected_version=2, target=WorkflowStatus.SUCCEEDED
    )
    service = AgentTaskService(
        SuccessfulRuntime(), state_machine=state_machine, workflow_store=store
    )

    with pytest.raises(RuntimeError, match="Cannot reconcile terminal workflow"):
        service.reconcile_workflow(
            "task-reconcile-conflict", principal_id="local-user"
        )

    store.close()
    state_machine.close()
