"""Planning and execution primitives that never call providers directly."""

from dataclasses import dataclass, field, replace
from enum import StrEnum
from time import monotonic
from typing import Any, Callable

from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest


class StepState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class PlanState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class Task:
    task_id: str
    principal_id: str
    title: str
    resource_scope: str
    max_steps: int = 32
    timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not all((self.task_id, self.principal_id, self.title, self.resource_scope)):
            raise ValueError("Task identifiers, title and resource_scope are required")
        if self.max_steps < 1 or self.timeout_seconds <= 0:
            raise ValueError("Task limits must be positive")


@dataclass(frozen=True, slots=True)
class PlanStep:
    step_id: str
    capability_id: str
    operation_id: str
    tool_name: str
    risk_level: RiskLevel
    arguments: dict[str, Any] = field(default_factory=dict)
    depends_on: frozenset[str] = frozenset()
    max_attempts: int = 1

    def __post_init__(self) -> None:
        if not all((self.step_id, self.capability_id, self.operation_id, self.tool_name)):
            raise ValueError("Plan step identifiers are required")
        if self.max_attempts < 1:
            raise ValueError("Plan step max_attempts must be positive")
        object.__setattr__(self, "depends_on", frozenset(self.depends_on))
        object.__setattr__(self, "arguments", dict(self.arguments))


@dataclass(frozen=True, slots=True)
class Plan:
    plan_id: str
    task_id: str
    steps: tuple[PlanStep, ...]

    def __post_init__(self) -> None:
        if not self.plan_id or not self.task_id or not self.steps:
            raise ValueError("Plan id, task id and steps are required")
        ids = [step.step_id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("Plan step IDs must be unique")
        unknown = set().union(*(step.depends_on for step in self.steps)) - set(ids)
        if unknown:
            raise ValueError(f"Plan has unknown dependencies: {', '.join(sorted(unknown))}")


@dataclass(frozen=True, slots=True)
class StepResult:
    step_id: str
    state: StepState
    attempts: int
    result: Any | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    plan_id: str
    state: PlanState
    steps: tuple[StepResult, ...]
    elapsed_seconds: float


class AgentExecutor:
    """Runs plans in stable order solely through MCPGateway."""

    def __init__(self, gateway: MCPGateway, event_bus: EventBus | None = None) -> None:
        self._gateway = gateway
        self._event_bus = event_bus

    async def execute(self, task: Task, plan: Plan, cancelled: Callable[[], bool] | None = None) -> ExecutionResult:
        if plan.task_id != task.task_id:
            raise ValueError("Plan does not belong to task")
        started = monotonic()
        completed: dict[str, StepResult] = {}
        for step in plan.steps:
            if cancelled is not None and cancelled():
                completed[step.step_id] = StepResult(step.step_id, StepState.CANCELLED, 0, reason="Task cancelled")
                continue
            if monotonic() - started > task.timeout_seconds:
                completed[step.step_id] = StepResult(step.step_id, StepState.CANCELLED, 0, reason="Task timed out")
                continue
            if any(completed[dependency].state is not StepState.SUCCEEDED for dependency in step.depends_on):
                completed[step.step_id] = StepResult(step.step_id, StepState.SKIPPED, 0, reason="Dependency did not succeed")
                continue
            self._event("PlanStepStarted", task, plan, step)
            result = await self._execute_step(task, plan, step)
            completed[step.step_id] = result
            self._event("PlanStepCompleted", task, plan, step, {"state": result.state, "attempts": result.attempts})
        results = tuple(completed[step.step_id] for step in plan.steps)
        state = PlanState.SUCCEEDED if all(item.state is StepState.SUCCEEDED for item in results) else PlanState.CANCELLED if any(item.state is StepState.CANCELLED for item in results) else PlanState.FAILED
        return ExecutionResult(plan.plan_id, state, results, monotonic() - started)

    async def _execute_step(self, task: Task, plan: Plan, step: PlanStep) -> StepResult:
        for attempt in range(1, step.max_attempts + 1):
            response = await self._gateway.invoke(MCPGatewayRequest(
                request_id=f"{plan.plan_id}:{step.step_id}:{attempt}", principal_id=task.principal_id,
                capability_id=step.capability_id, operation_id=step.operation_id,
                resource_scope=task.resource_scope, risk_level=step.risk_level,
                tool_name=step.tool_name, arguments=step.arguments, task_id=task.task_id,
            ))
            if response.decision is AuthorizationDecision.ALLOW:
                return StepResult(step.step_id, StepState.SUCCEEDED, attempt, response.result)
            return StepResult(step.step_id, StepState.FAILED, attempt, reason=response.reason)
        raise RuntimeError("Unreachable execution state")

    def _event(self, event_type: str, task: Task, plan: Plan, step: PlanStep, payload: dict[str, Any] | None = None) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(KernelEvent(event_type=event_type, source_component="agent_executor", correlation_id=plan.plan_id, payload={"task_id": task.task_id, "step_id": step.step_id, **(payload or {})}))


class AgentLoop:
    """Bounded deterministic planner/executor loop with optional replanning."""

    def __init__(self, executor: AgentExecutor, planner: Callable[[Task, int], Plan], max_cycles: int = 3) -> None:
        if max_cycles < 1:
            raise ValueError("max_cycles must be positive")
        self._executor, self._planner, self._max_cycles = executor, planner, max_cycles

    async def run(self, task: Task) -> ExecutionResult:
        latest: ExecutionResult | None = None
        for cycle in range(self._max_cycles):
            plan = self._planner(task, cycle)
            if len(plan.steps) > task.max_steps:
                raise ValueError("Plan exceeds task max_steps")
            latest = await self._executor.execute(task, plan)
            if latest.state is PlanState.SUCCEEDED:
                return latest
        if latest is None:
            raise RuntimeError("Agent loop produced no plan")
        return latest
