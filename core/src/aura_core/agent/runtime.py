"""Planning and execution primitives that never call providers directly."""

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from enum import StrEnum
from time import monotonic
from typing import Any, Callable

_request_id_context: ContextVar[str | None] = ContextVar("aura_request_id", default=None)

def _mcp_result_is_error(result: Any) -> bool:
    """Recognize MCP tool-level errors without trusting result payload as authority."""
    if isinstance(result, dict):
        return result.get("isError", result.get("is_error", False)) is True
    return (
        getattr(result, "isError", getattr(result, "is_error", False)) is True
    )


from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.memory.hierarchical_memory import ContextItem
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.enterprise.runtime_controls import BudgetExceeded, ExecutionBudget


_TEST_DATA_READ_OPERATION = (
    "filesystem.read_test_data",
    "filesystem.read_test_data",
    "read_file",
)
_ALLOWED_TEST_DATA_FILENAME = "governor-read-test.txt"


def validate_test_data_path(arguments: dict[str, Any] | None) -> None:
    """Reject every path except the exact test-data filename at execution time."""
    path = arguments.get("path") if isinstance(arguments, dict) else None
    if type(path) is not str or path != _ALLOWED_TEST_DATA_FILENAME:
        raise ValueError("Rejected path for test-data read")


def _validate_step_arguments(step: "PlanStep") -> None:
    if (step.capability_id, step.operation_id, step.tool_name) == _TEST_DATA_READ_OPERATION:
        validate_test_data_path(step.arguments)


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
    memory_context: tuple[ContextItem, ...] = ()

    def __post_init__(self) -> None:
        if not all((self.task_id, self.principal_id, self.title, self.resource_scope)):
            raise ValueError("Task identifiers, title and resource_scope are required")
        if self.max_steps < 1 or self.timeout_seconds <= 0:
            raise ValueError("Task limits must be positive")
        if len(self.memory_context) > 32 or any(not item.untrusted for item in self.memory_context):
            raise ValueError("Task memory context must be bounded and explicitly untrusted")


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
class CompensationStep:
    """Explicitly declared compensating operation; never auto-generated."""
    step_id: str
    compensates_step_id: str
    capability_id: str
    operation_id: str
    tool_name: str
    risk_level: RiskLevel
    arguments: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not all((self.step_id, self.compensates_step_id, self.capability_id,
                    self.operation_id, self.tool_name)):
            raise ValueError("Compensation step identifiers are required")
        object.__setattr__(self, "arguments", dict(self.arguments))


@dataclass(frozen=True, slots=True)
class Plan:
    plan_id: str
    task_id: str
    steps: tuple[PlanStep, ...]

    def __post_init__(self) -> None:
        if not self.plan_id or not self.task_id or not self.steps:
            raise ValueError("Plan id, task id and steps are required")

        original = list(self.steps)
        ids = [step.step_id for step in original]

        if len(ids) != len(set(ids)):
            raise ValueError("Plan step IDs must be unique")

        known = set(ids)
        unknown = set().union(
            *(step.depends_on for step in original)
        ) - known

        if unknown:
            raise ValueError(
                "Plan has unknown dependencies: "
                + ", ".join(sorted(unknown))
            )

        # Stable Kahn topological sort.
        pending = list(original)
        ordered: list[PlanStep] = []
        completed: set[str] = set()

        while pending:
            ready = [
                step for step in pending
                if step.depends_on.issubset(completed)
            ]

            if not ready:
                raise ValueError(
                    "Plan dependency cycle detected"
                )

            for step in ready:
                ordered.append(step)
                completed.add(step.step_id)
                pending.remove(step)

        object.__setattr__(self, "steps", tuple(ordered))

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
        """Execute independent dependency-ready steps concurrently, only via MCPGateway."""
        if plan.task_id != task.task_id:
            raise ValueError("Plan does not belong to task")
        started = monotonic()
        budget = ExecutionBudget(
            max_steps=task.max_steps,
            max_tool_calls=task.max_steps,
            deadline_monotonic=started + task.timeout_seconds,
        )
        completed: dict[str, StepResult] = {}
        pending = list(plan.steps)
        capacity = max(1, min(8, int(__import__("os").getenv("AURA_MAX_PARALLEL_STEPS", "4"))))
        semaphore = asyncio.Semaphore(capacity)

        async def run_step(step: PlanStep) -> StepResult:
            async with semaphore:
                self._event("PlanStepStarted", task, plan, step)
                remaining = task.timeout_seconds - (monotonic() - started)
                if remaining <= 0:
                    result = StepResult(step.step_id, StepState.CANCELLED, 0, reason="Task timed out")
                else:
                    execution = asyncio.create_task(self._execute_step(task, plan, step, budget=budget, cancelled=cancelled))
                    deadline = monotonic() + remaining
                    try:
                        while not execution.done():
                            if cancelled is not None and cancelled():
                                execution.cancel()
                                await asyncio.gather(execution, return_exceptions=True)
                                result = StepResult(step.step_id, StepState.CANCELLED, 0, reason="Task cancelled")
                                break
                            time_left = deadline - monotonic()
                            if time_left <= 0:
                                execution.cancel()
                                await asyncio.gather(execution, return_exceptions=True)
                                result = StepResult(step.step_id, StepState.CANCELLED, 0, reason="Task timed out")
                                break
                            try:
                                await asyncio.wait_for(asyncio.shield(execution), timeout=min(0.05, time_left))
                            except asyncio.TimeoutError:
                                continue
                        else:
                            result = execution.result()
                    except asyncio.CancelledError:
                        execution.cancel()
                        await asyncio.gather(execution, return_exceptions=True)
                        raise
                self._event("PlanStepCompleted", task, plan, step, {
                    "state": result.state.value, "attempts": result.attempts
                })
                return result

        while pending:
            if cancelled is not None and cancelled():
                for step in pending:
                    completed[step.step_id] = StepResult(step.step_id, StepState.CANCELLED, 0, reason="Task cancelled")
                pending.clear()
                break
            if monotonic() - started >= task.timeout_seconds:
                for step in pending:
                    completed[step.step_id] = StepResult(step.step_id, StepState.CANCELLED, 0, reason="Task timed out")
                pending.clear()
                break

            ready = [step for step in pending if step.depends_on.issubset(completed)]
            if not ready:
                # Plan validates dependencies/cycles, so this is defensive only.
                for step in pending:
                    completed[step.step_id] = StepResult(step.step_id, StepState.SKIPPED, 0, reason="Dependencies could not be resolved")
                break

            runnable: list[PlanStep] = []
            for step in ready:
                if any(completed[dep].state is not StepState.SUCCEEDED for dep in step.depends_on):
                    completed[step.step_id] = StepResult(step.step_id, StepState.SKIPPED, 0, reason="Dependency did not succeed")
                else:
                    runnable.append(step)
                pending.remove(step)

            if runnable:
                outcomes = await asyncio.gather(*(run_step(step) for step in runnable), return_exceptions=True)
                for step, outcome in zip(runnable, outcomes):
                    if isinstance(outcome, asyncio.CancelledError):
                        raise outcome
                    if isinstance(outcome, BaseException):
                        completed[step.step_id] = StepResult(
                            step.step_id, StepState.FAILED, 0,
                            reason=f"Step execution failed: {type(outcome).__name__}",
                        )
                    else:
                        completed[step.step_id] = outcome

        results = tuple(completed[step.step_id] for step in plan.steps)
        state = PlanState.SUCCEEDED if all(item.state is StepState.SUCCEEDED for item in results) else PlanState.CANCELLED if any(item.state is StepState.CANCELLED for item in results) else PlanState.FAILED
        if self._event_bus is not None:
            self._event_bus.publish(
                KernelEvent(
                    event_type="TaskSucceeded" if state is PlanState.SUCCEEDED else "TaskFailed",
                    source_component="agent_executor",
                    correlation_id=plan.plan_id,
                    payload={
                        "task_id": task.task_id,
                        "plan_id": plan.plan_id,
                        "state": state.value,
                        "failed_steps": [item.step_id for item in results if item.state is not StepState.SUCCEEDED],
                        "parallel_capacity": capacity,
                    },
                    metadata={"request_id": _request_id_context.get()} if _request_id_context.get() else {},
                )
            )
        return ExecutionResult(plan.plan_id, state, results, monotonic() - started)

    async def execute_compensations(
        self, task: Task, plan_id: str, steps: tuple[CompensationStep, ...]
    ) -> tuple[StepResult, ...]:
        """Run only caller-declared compensations, with each call re-authorized by MCPGateway.

        This method is deliberately explicit and is never invoked automatically on failure.
        """
        seen: set[str] = set()
        results: list[StepResult] = []
        for step in steps:
            if step.step_id in seen:
                raise ValueError("Compensation step IDs must be unique")
            seen.add(step.step_id)
            self._event_compensation("CompensationStarted", task, plan_id, step)
            if (step.capability_id, step.operation_id, step.tool_name) == _TEST_DATA_READ_OPERATION:
                validate_test_data_path(step.arguments)
            response = await self._gateway.invoke(MCPGatewayRequest(
                request_id=f"{plan_id}:compensation:{step.step_id}",
                principal_id=task.principal_id,
                capability_id=step.capability_id,
                operation_id=step.operation_id,
                resource_scope=task.resource_scope,
                risk_level=step.risk_level,
                tool_name=step.tool_name,
                arguments=step.arguments,
                task_id=task.task_id,
            ))
            state = StepState.SUCCEEDED if response.decision is AuthorizationDecision.ALLOW else StepState.FAILED
            result = StepResult(
                step.step_id, state, 1, response.result,
                reason="" if state is StepState.SUCCEEDED else response.reason,
            )
            results.append(result)
            self._event_compensation("CompensationCompleted", task, plan_id, step, {
                "state": state.value, "compensates_step_id": step.compensates_step_id
            })
            if state is StepState.FAILED:
                # Do not proceed into additional compensations after a denied operation.
                break
        return tuple(results)

    def _event_compensation(
        self, event_type: str, task: Task, plan_id: str, step: CompensationStep,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if self._event_bus is None:
            return
        payload = {
            "task_id": task.task_id,
            "compensation_step_id": step.step_id,
            "compensates_step_id": step.compensates_step_id,
            **(extra or {}),
        }
        request_id = _request_id_context.get()
        self._event_bus.publish(KernelEvent(
            event_type=event_type,
            source_component="agent_executor",
            correlation_id=plan_id,
            payload=payload,
            metadata={"request_id": request_id} if request_id else {},
        ))

    async def _execute_step(
        self, task: Task, plan: Plan, step: PlanStep,
        *, budget: ExecutionBudget | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> StepResult:
        _validate_step_arguments(step)
        if budget is not None:
            budget.consume_step(cancelled=cancelled() if cancelled is not None else False)
        for attempt in range(1, step.max_attempts + 1):
            if budget is not None:
                budget.check(cancelled=cancelled() if cancelled is not None else False)
                budget.consume_tool_call()
            response = await self._gateway.invoke(MCPGatewayRequest(
                request_id=f"{plan.plan_id}:{step.step_id}:{attempt}", principal_id=task.principal_id,
                capability_id=step.capability_id, operation_id=step.operation_id,
                resource_scope=task.resource_scope, risk_level=step.risk_level,
                tool_name=step.tool_name, arguments=step.arguments, task_id=task.task_id,
            ))
            if response.decision is AuthorizationDecision.ALLOW:
                if _mcp_result_is_error(response.result):
                    return StepResult(
                        step.step_id,
                        StepState.FAILED,
                        attempt,
                        result=response.result,
                        reason="MCP tool returned an error result",
                    )
                return StepResult(step.step_id, StepState.SUCCEEDED, attempt, response.result)
            return StepResult(step.step_id, StepState.FAILED, attempt, reason=response.reason)
        raise RuntimeError("Unreachable execution state")

    def _event(self, event_type: str, task: Task, plan: Plan, step: PlanStep, payload: dict[str, Any] | None = None) -> None:
        if self._event_bus is not None:
            request_id = _request_id_context.get()
            metadata = {"request_id": request_id} if request_id else {}
            self._event_bus.publish(
                KernelEvent(
                    event_type=event_type,
                    source_component="agent_executor",
                    correlation_id=plan.plan_id,
                    payload={
                        "task_id": task.task_id,
                        "step_id": step.step_id,
                        **(payload or {}),
                    },
                    metadata=metadata,
                )
            )


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
