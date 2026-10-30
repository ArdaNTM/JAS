"""Failure reflection proposes recovery; it never executes tools."""
from __future__ import annotations
import inspect
from typing import Any, Callable
from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.application.task_state_machine import TaskState

class ReflectionService:
    def __init__(self, event_bus: EventBus, task_states: Any,
                 planner: Callable[[dict[str, Any]], Any], *, max_error_chars: int = 1200):
        self.event_bus = event_bus
        self.task_states = task_states
        self.planner = planner
        self.max_error_chars = max_error_chars
        self._unsubscribe = event_bus.subscribe("ToolExecutionFailed", self.handle_failure)

    async def _call(self, method, *args, **kwargs):
        result = method(*args, **kwargs)
        return await result if inspect.isawaitable(result) else result

    async def handle_failure(self, event: KernelEvent) -> None:
        payload = dict(event.payload)
        task_id, principal_id = payload.get("task_id"), payload.get("principal_id")
        if not task_id or not principal_id:
            return
        try:
            record = await self._call(self.task_states.get, str(task_id), principal_id=str(principal_id))
        except KeyError:
            return
        if record.state == TaskState.RUNNING:
            record = await self._call(self.task_states.transition, record.task_id,
                principal_id=record.principal_id, target=TaskState.COMPENSATING,
                error="MCP tool failed; reflection proposal requested")
        if record.state != TaskState.COMPENSATING:
            return
        safe = {key: payload.get(key) for key in (
            "task_id", "principal_id", "capability_id", "provider_id", "tool_name",
            "failure_type", "http_status",
        )}
        safe["error_summary"] = str(payload.get("error_summary", ""))[:self.max_error_chars]
        plan = self.planner(safe)
        if inspect.isawaitable(plan):
            plan = await plan
        self.event_bus.publish(KernelEvent(
            event_type="ReflectionPlanReady", source_component="aura.reflection",
            payload={"task_id":record.task_id, "principal_id":record.principal_id,
                     "plan":plan if isinstance(plan, dict) else {},
                     "state":TaskState.COMPENSATING.value},
            correlation_id=record.task_id,
        ))

    def close(self) -> None:
        self._unsubscribe()
