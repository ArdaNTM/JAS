"""Agent runtime that validates discovery/selection before gateway execution."""

from aura_core.agent.runtime import AgentExecutor, ExecutionResult, Plan, Task
from aura_core.discovery.service import ToolDiscoveryRequest, ToolDiscoveryService, ToolSelectionService
from aura_core.kernel.events import EventBus, KernelEvent


class CapabilityAgentRuntime:
    """Connect planner output to discovery while preserving the gateway boundary."""

    def __init__(self, executor: AgentExecutor, discovery: ToolDiscoveryService, selector: ToolSelectionService, event_bus: EventBus | None = None) -> None:
        self._executor = executor
        self._discovery = discovery
        self._selector = selector
        self._event_bus = event_bus

    async def execute(self, task: Task, plan: Plan) -> ExecutionResult:
        for step in plan.steps:
            candidates = self._discovery.discover(ToolDiscoveryRequest(step.capability_id, step.operation_id, frozenset({step.tool_name})))
            selected = self._selector.select(candidates)
            if selected.tool_name != step.tool_name:
                raise LookupError("Selected tool does not match planned tool")
            self._publish("ToolSelected", task.task_id, step.step_id, selected.provider_id, selected.tool_name)
        self._publish("TaskStarted", task.task_id)
        result = await self._executor.execute(task, plan)
        self._publish("TaskCompleted" if result.state.value == "succeeded" else "TaskFailed", task.task_id)
        return result

    def _publish(self, event_type: str, task_id: str, step_id: str | None = None, provider_id: str | None = None, tool_name: str | None = None) -> None:
        if self._event_bus is not None:
            payload = {"task_id": task_id}
            if step_id is not None:
                payload["step_id"] = step_id
            if provider_id is not None:
                payload["provider_id"] = provider_id
            if tool_name is not None:
                payload["tool_name"] = tool_name
            self._event_bus.publish(KernelEvent(event_type=event_type, source_component="capability_agent_runtime", payload=payload))
