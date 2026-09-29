"""HTTP-facing task coordination over the boundary-enforced agent runtime."""

from dataclasses import dataclass
from typing import Protocol

from aura_core.agent.runtime import ExecutionResult, Plan, Task


class TaskRuntime(Protocol):
    async def execute(self, task: Task, plan: Plan) -> ExecutionResult:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class SubmittedTask:
    task: Task
    plan: Plan


class AgentTaskService:
    """Coordinates a fully specified plan without exposing providers to HTTP."""

    def __init__(self, runtime: TaskRuntime) -> None:
        self._runtime = runtime
        self._results: dict[str, ExecutionResult] = {}

    async def submit(self, submitted: SubmittedTask) -> ExecutionResult:
        if submitted.task.task_id in self._results:
            raise ValueError(f"Task already submitted: {submitted.task.task_id}")
        result = await self._runtime.execute(submitted.task, submitted.plan)
        self._results[submitted.task.task_id] = result
        return result

    def get(self, task_id: str) -> ExecutionResult:
        try:
            return self._results[task_id]
        except KeyError as exc:
            raise KeyError(f"Unknown task: {task_id}") from exc
