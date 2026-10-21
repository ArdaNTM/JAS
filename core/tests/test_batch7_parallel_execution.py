from __future__ import annotations

import asyncio
from types import SimpleNamespace

from aura_core.agent.runtime import AgentExecutor, Plan, PlanStep, Task
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel


class ConcurrentGateway:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.finished: set[str] = set()
        self.dependency_was_ready = False

    async def invoke(self, request):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if request.tool_name == "dependent":
                self.dependency_was_ready = {"first", "second"}.issubset(self.finished)
            await asyncio.sleep(0.03)
            self.finished.add(request.tool_name)
            return SimpleNamespace(
                decision=AuthorizationDecision.ALLOW,
                result={"tool": request.tool_name},
                reason="allowed",
            )
        finally:
            self.active -= 1


def step(step_id: str, tool_name: str, depends_on: frozenset[str] = frozenset()) -> PlanStep:
    return PlanStep(
        step_id=step_id,
        capability_id="test.capability",
        operation_id="test.operation",
        tool_name=tool_name,
        risk_level=RiskLevel.LOW,
        depends_on=depends_on,
    )


def test_independent_steps_run_concurrently_and_dependencies_wait() -> None:
    async def scenario() -> None:
        gateway = ConcurrentGateway()
        executor = AgentExecutor(gateway)  # type: ignore[arg-type]
        task = Task("task-7", "local-user", "parallel plan", "local", timeout_seconds=2)
        plan = Plan(
            "plan-7",
            task.task_id,
            (
                step("one", "first"),
                step("two", "second"),
                step("three", "dependent", frozenset({"one", "two"})),
            ),
        )
        result = await executor.execute(task, plan)
        assert result.state.value == "succeeded"
        assert gateway.max_active >= 2
        assert gateway.dependency_was_ready

    asyncio.run(scenario())
