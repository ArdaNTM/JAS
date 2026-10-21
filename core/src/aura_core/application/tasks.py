"""HTTP-facing task coordination over the boundary-enforced agent runtime."""

import asyncio
from dataclasses import dataclass, replace
from typing import Protocol

from aura_core.agent.runtime import ExecutionResult, Plan, Task, _request_id_context
from aura_core.application.task_memory import TaskMemoryCoordinator


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

    def __init__(self, runtime: TaskRuntime, *, memory: TaskMemoryCoordinator | None = None) -> None:
        self._runtime = runtime
        self._memory = memory
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

            task = submitted.task
            memory_started = False
            if self._memory is not None:
                context = self._memory.begin(
                    principal_id=task.principal_id,
                    task_id=task.task_id,
                    goal=task.title,
                )
                # Context is attached as data and explicitly marked untrusted;
                # it never changes gateway arguments or authorization decisions.
                task = replace(task, memory_context=context)
                memory_started = True

            token = _request_id_context.set(submitted.request_id)
            try:
                result = await self._runtime.execute(task, submitted.plan)
            except BaseException:
                if memory_started and self._memory is not None:
                    self._memory.finish(
                        principal_id=task.principal_id, task_id=task.task_id,
                        state="failed", summary="Task runtime raised an exception.",
                    )
                raise
            finally:
                _request_id_context.reset(token)

            if memory_started and self._memory is not None:
                state = getattr(result.state, "value", str(result.state)).lower()
                memory_state = state if state in {"succeeded", "failed", "cancelled"} else "failed"
                summary = "; ".join(
                    f"{step.step_id}:{getattr(step.state, 'value', step.state)}"
                    for step in result.steps
                )[:4000]
                self._memory.finish(
                    principal_id=task.principal_id, task_id=task.task_id,
                    state=memory_state, summary=summary,
                )

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
