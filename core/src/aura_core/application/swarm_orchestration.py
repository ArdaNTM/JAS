"""Bounded specialist orchestration; EventBus messages are data, not authority."""
from __future__ import annotations

import json
import math
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
        if type(max_steps) is not int or not 1 <= max_steps <= 32:
            raise ValueError("max_steps must be between 1 and 32")
        self.gateway = gateway
        self.events = event_bus
        self.max_steps = max_steps

    def _preflight(self, principal_id: str, task_id: str,
                   steps: tuple[SpecialistStep, ...]) -> None:
        """Validate all requested specialists before any MCP dispatch."""
        def identity(value: object) -> None:
            if (type(value) is not str or not 1 <= len(value) <= 200
                    or value != value.strip() or any(ord(ch) < 32 for ch in value)):
                raise ValueError("invalid swarm identity")
        identity(principal_id)
        identity(task_id)
        if not isinstance(steps, (list, tuple)) or not 1 <= len(steps) <= self.max_steps:
            raise ValueError("invalid swarm step count")
        nodes = 0
        def validate_json(value: Any, depth: int = 0) -> None:
            nonlocal nodes
            nodes += 1
            if nodes > 1000 or depth > 10:
                raise ValueError("swarm JSON complexity budget exceeded")
            if value is None or type(value) is bool:
                return
            if type(value) is str:
                if len(value) > 8192:
                    raise ValueError("swarm argument text too long")
                return
            if type(value) in (int, float):
                if not math.isfinite(value) or abs(value) > 1e18:
                    raise ValueError("non-finite or unbounded numeric argument")
                return
            if type(value) is list:
                if len(value) > 128:
                    raise ValueError("swarm list too long")
                for item in value:
                    validate_json(item, depth + 1)
                return
            if type(value) is dict:
                if len(value) > 64:
                    raise ValueError("swarm object too large")
                for key, item in value.items():
                    if type(key) is not str or not 1 <= len(key) <= 120:
                        raise ValueError("invalid swarm argument key")
                    validate_json(item, depth + 1)
                return
            raise ValueError("unsupported swarm JSON input")
        for step in steps:
            if type(step) is not SpecialistStep or step.role not in self.ROLES:
                raise ValueError("unsupported specialist")
            for field in ("capability_id", "operation_id", "resource_scope", "tool_name"):
                identity(getattr(step, field))
            if type(step.arguments) is not dict:
                raise ValueError("swarm arguments must be an object")
            validate_json(step.arguments)
            try:
                encoded = json.dumps(step.arguments, ensure_ascii=False, allow_nan=False)
            except (TypeError, ValueError, RecursionError, OverflowError) as exc:
                raise ValueError("invalid swarm JSON arguments") from exc
            if len(encoded.encode("utf-8")) > 32768:
                raise ValueError("swarm argument byte budget exceeded")

    async def execute(self, *, principal_id: str, task_id: str,
                      steps: tuple[SpecialistStep, ...]):
        self._preflight(principal_id, task_id, steps)
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
