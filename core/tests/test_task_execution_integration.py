from __future__ import annotations

import asyncio

import pytest

from aura_core.agent.runtime import (
    AgentExecutor, CompensationStep, ExecutionResult, Plan, PlanState, PlanStep,
    StepResult, StepState, Task,
)
from aura_core.application.task_state_machine import TaskState, TaskStateMachine
from aura_core.application.tasks import AgentTaskService, SubmittedTask
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.mcp.gateway import MCPGatewayResponse


def make_task(task_id: str, timeout: float = 1.0) -> Task:
    return Task(task_id, "principal:test", task_id, "workspace:test", timeout_seconds=timeout)


def make_plan(task_id: str) -> Plan:
    return Plan(f"plan-{task_id}", task_id, (
        PlanStep("step-1", "capability.read", "read", "read_file", RiskLevel.LOW),
    ))


class OrderedRuntime:
    def __init__(self):
        self.started = []

    async def execute(self, task, plan, cancelled=None):
        self.started.append(task.task_id)
        await asyncio.sleep(0)
        return ExecutionResult(plan.plan_id, PlanState.SUCCEEDED,
                               (StepResult("step-1", StepState.SUCCEEDED, 1),), 0.0)


def test_agent_task_service_executes_dependency_chain_in_order(tmp_path):
    async def scenario():
        machine = TaskStateMachine(tmp_path / "chain.sqlite3")
        runtime = OrderedRuntime()
        service = AgentTaskService(runtime, state_machine=machine)
        parent = SubmittedTask(make_task("parent"), make_plan("parent"))
        child = SubmittedTask(make_task("child"), make_plan("child"), dependencies=("parent",))
        results = await service.submit_chain((parent, child))
        assert [result.state for result in results] == [PlanState.SUCCEEDED, PlanState.SUCCEEDED]
        assert runtime.started == ["parent", "child"]
        assert machine.get("parent", principal_id="principal:test").state == TaskState.SUCCEEDED
        assert machine.get("child", principal_id="principal:test").state == TaskState.SUCCEEDED
        machine.close()
    asyncio.run(scenario())


def test_single_submit_refuses_unready_dependency(tmp_path):
    async def scenario():
        machine = TaskStateMachine(tmp_path / "blocked.sqlite3")
        machine.create_task(principal_id="principal:test", task_id="parent", goal="parent")
        machine.create_task(principal_id="principal:test", task_id="child", goal="child", dependencies=("parent",))
        service = AgentTaskService(OrderedRuntime(), state_machine=machine)
        child = SubmittedTask(make_task("child"), make_plan("child"), dependencies=("parent",))
        with pytest.raises(RuntimeError, match="dependencies"):
            await service.submit(child)
        machine.close()
    asyncio.run(scenario())


def test_timeout_is_enforced_and_persisted(tmp_path):
    class SlowRuntime:
        async def execute(self, task, plan, cancelled=None):
            await asyncio.sleep(10)
            return ExecutionResult(plan.plan_id, PlanState.SUCCEEDED, (), 10.0)

    async def scenario():
        machine = TaskStateMachine(tmp_path / "timeout.sqlite3")
        service = AgentTaskService(SlowRuntime(), state_machine=machine)
        submitted = SubmittedTask(make_task("slow", timeout=0.03), make_plan("slow"))
        with pytest.raises(asyncio.TimeoutError):
            await service.submit(submitted)
        assert machine.get("slow", principal_id="principal:test").state == TaskState.TIMED_OUT
        machine.close()
    asyncio.run(scenario())


def test_cooperative_cancel_stops_runtime_and_persists_state(tmp_path):
    class CooperativeRuntime:
        async def execute(self, task, plan, cancelled=None):
            while not cancelled():
                await asyncio.sleep(0.005)
            return ExecutionResult(plan.plan_id, PlanState.CANCELLED,
                                   (StepResult("step-1", StepState.CANCELLED, 0),), 0.01)

    async def scenario():
        machine = TaskStateMachine(tmp_path / "cancel.sqlite3")
        service = AgentTaskService(CooperativeRuntime(), state_machine=machine)
        submitted = SubmittedTask(make_task("cancel-me"), make_plan("cancel-me"))
        running = asyncio.create_task(service.submit(submitted))
        for _ in range(100):
            await asyncio.sleep(0.002)
            try:
                if machine.get("cancel-me", principal_id="principal:test").state == TaskState.RUNNING:
                    break
            except KeyError:
                pass
        service.cancel("cancel-me", principal_id="principal:test")
        result = await running
        assert result.state == PlanState.CANCELLED
        assert machine.get("cancel-me", principal_id="principal:test").state == TaskState.CANCELLED
        machine.close()
    asyncio.run(scenario())


def test_compensation_is_explicit_and_gateway_authorized():
    class Gateway:
        def __init__(self):
            self.requests = []
        async def invoke(self, request):
            self.requests.append(request)
            return MCPGatewayResponse(AuthorizationDecision.DENY, None, "mcp:test",
                                      request.tool_name, "permission denied")

    async def scenario():
        gateway = Gateway()
        executor = AgentExecutor(gateway)
        compensation = CompensationStep(
            step_id="undo-write", compensates_step_id="write",
            capability_id="filesystem.write", operation_id="delete_created_file",
            tool_name="delete_file", risk_level=RiskLevel.HIGH,
            arguments={"path": "workspace:test/new.txt"},
        )
        results = await executor.execute_compensations(
            make_task("rollback"), "plan-rollback", (compensation,)
        )
        assert len(gateway.requests) == 1
        assert gateway.requests[0].tool_name == "delete_file"
        assert results[0].state is StepState.FAILED
        assert results[0].reason == "permission denied"
    asyncio.run(scenario())
