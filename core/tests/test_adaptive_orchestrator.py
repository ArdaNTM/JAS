import pytest

from aura_core.agent.runtime import ExecutionResult, PlanState, StepResult, StepState
from aura_core.application.adaptive_orchestrator import AdaptiveTaskOrchestrator
from aura_core.agent.runtime import Plan, Task


class FakeTaskService:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.task_ids = []

    async def submit(self, submitted):
        self.task_ids.append(submitted.task.task_id)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _task(attempt):
    return Task(
        task_id=f"task-{attempt}",
        principal_id="local_owner",
        title="research",
        resource_scope="public-web",
    )


def _plan(task, attempt):
    from aura_core.agent.runtime import PlanStep
    from aura_core.kernel.permissions import RiskLevel
    return Plan(
        plan_id=f"plan-{task.task_id}",
        task_id=task.task_id,
        steps=(PlanStep(
            step_id="research",
            capability_id="internet.search",
            operation_id="internet.search",
            tool_name="search",
            risk_level=RiskLevel.LOW,
        ),),
    )


def _result(task_id, state=PlanState.SUCCEEDED, reason="", result={"items": [1]}):
    step = StepResult(
        step_id="research",
        state=StepState.SUCCEEDED if state is PlanState.SUCCEEDED else StepState.FAILED,
        attempts=1,
        result=result if state is PlanState.SUCCEEDED else None,
        reason=reason,
    )
    return ExecutionResult(f"plan:{task_id}", state, (step,), 0.01)


@pytest.mark.asyncio
async def test_transient_failure_retries_once_as_new_governed_task():
    service = FakeTaskService([ConnectionError("network temporarily unavailable"), _result("task-1")])
    run = await AdaptiveTaskOrchestrator().run(
        service, _task, _plan, request_id="request-1"
    )
    assert run.execution.state is PlanState.SUCCEEDED
    assert len(service.task_ids) == 2
    assert service.task_ids == ["task-0", "task-1"]
    assert run.recovery[0]["action"] == "replan_once"


@pytest.mark.asyncio
async def test_authorization_denial_is_not_retried():
    service = FakeTaskService([_result("task-0", PlanState.FAILED, "Permission denied")])
    run = await AdaptiveTaskOrchestrator().run(
        service, _task, _plan, request_id="request-1"
    )
    assert run.execution.state is PlanState.FAILED
    assert len(service.task_ids) == 1
    assert run.recovery[0]["authorization_denied"] is True
    assert run.recovery[0]["action"] == "stop"


@pytest.mark.asyncio
async def test_unknown_exception_is_not_retried():
    service = FakeTaskService([RuntimeError("unknown runtime failure")])
    with pytest.raises(RuntimeError):
        await AdaptiveTaskOrchestrator().run(
            service, _task, _plan, request_id="request-1"
        )
    assert len(service.task_ids) == 1
