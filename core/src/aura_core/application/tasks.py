"""HTTP-facing task coordination over the boundary-enforced agent runtime."""

import asyncio
from dataclasses import dataclass
from typing import Protocol

from aura_core.agent.runtime import ExecutionResult, Plan, Task, _request_id_context


class TaskRuntime(Protocol):
    async def execute(self, task: Task, plan: Plan) -> ExecutionResult:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class SubmittedTask:
    task: Task
    plan: Plan
    request_id: str | None = None


class AgentTaskService:
    """Coordinates plans without exposing providers to HTTP."""

    def __init__(self, runtime: TaskRuntime) -> None:
        self._runtime = runtime
        self._results: dict[str, ExecutionResult] = {}
        self._owners: dict[str, str] = {}
        self._task_locks: dict[str, asyncio.Lock] = {}

    async def submit(self, submitted: SubmittedTask) -> ExecutionResult:
        task_id = submitted.task.task_id

        # Lock creation occurs before the first await. Requests for
        # different task IDs can proceed independently.
        lock = self._task_locks.setdefault(task_id, asyncio.Lock())

        async with lock:
            if task_id in self._results:
                raise ValueError(f"Task already submitted: {task_id}")

            token = _request_id_context.set(submitted.request_id)
            try:
                result = await self._runtime.execute(
                    submitted.task,
                    submitted.plan,
                )
            finally:
                _request_id_context.reset(token)

            self._results[task_id] = result
            self._owners[task_id] = submitted.task.principal_id
            return result

    def get_for_owner(
        self,
        task_id: str,
        principal_id: str,
    ) -> ExecutionResult:
        if self._owners.get(task_id) != principal_id:
            raise KeyError(f"Unknown task: {task_id}")
        return self.get(task_id)

    def get(self, task_id: str) -> ExecutionResult:
        try:
            return self._results[task_id]
        except KeyError as exc:
            raise KeyError(f"Unknown task: {task_id}") from exc
