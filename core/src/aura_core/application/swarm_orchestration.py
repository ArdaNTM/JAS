"""Bounded specialist orchestration; EventBus messages are data, not authority."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any
from uuid import uuid4

from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel


@dataclass(frozen=True)
class SpecialistStep:
    role: str
    capability_id: str
    operation_id: str
    resource_scope: str
    tool_name: str
    arguments: dict[str, Any]



def _admit_arguments(arguments: object) -> None:
    """Reject non-JSON, cyclic, nonfinite and oversized input before any dispatch."""
    if type(arguments) is not dict:
        raise ValueError("Specialist arguments must be a plain object")
    active: set[int] = set()
    budget = [0]

    def walk(value: object, depth: int) -> None:
        budget[0] += 1
        if depth > 12 or budget[0] > 4096:
            raise ValueError("Specialist arguments exceed bounded limits")
        if value is None or type(value) is bool:
            return
        if type(value) is str:
            if len(value) > 32768:
                raise ValueError("Specialist argument text too long")
            return
        if type(value) is int:
            if abs(value) > (1 << 63) - 1:
                raise ValueError("Specialist integer out of range")
            return
        if type(value) is float:
            if not math.isfinite(value):
                raise ValueError("Nonfinite specialist number")
            return
        if type(value) not in (dict, list):
            raise ValueError("Non-JSON specialist argument")
        if len(value) > 1000 or id(value) in active:
            raise ValueError("Cyclic or oversized specialist arguments")
        active.add(id(value))
        try:
            if type(value) is dict:
                for key, item in value.items():
                    if type(key) is not str or len(key) > 256:
                        raise ValueError("Invalid specialist argument key")
                    walk(item, depth + 1)
            else:
                for item in value:
                    walk(item, depth + 1)
        finally:
            active.remove(id(value))

    walk(arguments, 0)


def _admit_step(step: object, roles: frozenset[str]) -> None:
    if type(step) is not SpecialistStep or step.role not in roles:
        raise ValueError("Unsupported specialist")
    for field in ("capability_id", "operation_id", "resource_scope", "tool_name"):
        value = getattr(step, field)
        if type(value) is not str or not value.strip() or len(value) > 256:
            raise ValueError(f"Invalid specialist {field}")
    _admit_arguments(step.arguments)


class SwarmOrchestrator:
    """An explicit approved plan runner. No autonomous tool or policy creation."""

    ROLES = frozenset({"coder", "researcher"})

    def __init__(self, *, gateway: MCPGateway, event_bus: EventBus, max_steps: int = 8):
        if type(max_steps) is not int or not 1 <= max_steps <= 32:
            raise ValueError("max_steps must be between 1 and 32")
        self.gateway = gateway
        self.events = event_bus
        self.max_steps = max_steps

    async def execute(self, *, principal_id: str, task_id: str,
                      steps: tuple[SpecialistStep, ...]):
        if (type(principal_id) is not str or not principal_id.strip()
                or type(task_id) is not str or not task_id.strip()
                or type(steps) is not tuple or not 1 <= len(steps) <= self.max_steps):
            raise ValueError("Invalid swarm request")
        # Whole-plan admission precedes every EventBus emission and Gateway call.
        for step in steps:
            _admit_step(step, self.ROLES)
        outcomes = []
        for index, step in enumerate(steps):
            self.events.publish(KernelEvent(
                event_type="SwarmStepRequested", source_component="aura.swarm",
                correlation_id=task_id, payload={
                    "principal_id": principal_id, "task_id": task_id,
                    "role": step.role, "index": index,
                    "capability_id": step.capability_id,
                }))
            response = await self.gateway.invoke(MCPGatewayRequest(
                request_id=str(uuid4()), principal_id=principal_id,
                capability_id=step.capability_id, operation_id=step.operation_id,
                resource_scope=step.resource_scope, risk_level=RiskLevel.MEDIUM,
                tool_name=step.tool_name, arguments=step.arguments, task_id=task_id))
            outcomes.append(response)
            self.events.publish(KernelEvent(
                event_type="SwarmStepCompleted", source_component="aura.swarm",
                correlation_id=task_id, payload={
                    "principal_id": principal_id, "task_id": task_id,
                    "role": step.role, "index": index,
                    "decision": response.decision.value,
                }))
            if response.decision is not AuthorizationDecision.ALLOW:
                break
        return tuple(outcomes)
