"""Bounded specialist orchestration; EventBus messages are data, not authority."""
from __future__ import annotations

from dataclasses import dataclass
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


class SwarmOrchestrator:
    """An explicit approved plan runner. No autonomous tool or policy creation."""

    ROLES = frozenset({"coder", "researcher"})

    def __init__(self, *, gateway: MCPGateway, event_bus: EventBus, max_steps: int = 8):
        if not 1 <= max_steps <= 32:
            raise ValueError("max_steps must be between 1 and 32")
        self.gateway = gateway
        self.events = event_bus
        self.max_steps = max_steps

    async def execute(self, *, principal_id: str, task_id: str,
                      steps: tuple[SpecialistStep, ...]):
        if not principal_id or not task_id or not 1 <= len(steps) <= self.max_steps:
            raise ValueError("Invalid swarm request")
        outcomes = []
        for index, step in enumerate(steps):
            if step.role not in self.ROLES:
                raise ValueError("Unsupported specialist")
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
