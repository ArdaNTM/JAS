"""Capability-driven, deterministic MCP tool discovery and selection."""

from dataclasses import dataclass

from aura_core.kernel.capabilities import CapabilityRegistry, LatencyClass, QualityClass
from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.mcp.tool_registry import MCPToolRecord, MCPToolRegistry


@dataclass(frozen=True, slots=True)
class ToolDiscoveryRequest:
    """A non-executing request for tools implementing one capability."""

    capability_id: str
    operation_id: str
    requested_tool_names: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.capability_id:
            raise ValueError("Tool discovery capability_id is required")
        if not self.operation_id:
            raise ValueError("Tool discovery operation_id is required")
        object.__setattr__(self, "requested_tool_names", frozenset(self.requested_tool_names))


@dataclass(frozen=True, slots=True)
class ToolCandidate:
    """An available, registered MCP tool associated with a capability."""

    capability_id: str
    operation_id: str
    provider_id: str
    tool_name: str
    priority: int
    quality_class: QualityClass
    latency_class: LatencyClass
    record: MCPToolRecord


class ToolDiscoveryService:
    """Read-only join between capability and MCP tool registries.

    Discovery does not resolve provider instances or evaluate policies because
    it has no side effect. A candidate used for execution must still go through
    MCPGateway and PermissionEngine.
    """

    def __init__(self, capability_registry: CapabilityRegistry, tool_registry: MCPToolRegistry, event_bus: EventBus | None = None) -> None:
        self._capability_registry = capability_registry
        self._tool_registry = tool_registry
        self._event_bus = event_bus

    def discover(self, request: ToolDiscoveryRequest) -> tuple[ToolCandidate, ...]:
        candidates: list[ToolCandidate] = []
        for capability in self._capability_registry.providers(request.capability_id):
            definition = capability.definition
            if not capability.available or not capability.healthy or definition.provider_type.value != "mcp":
                continue
            for record in self._tool_registry.tools_for_provider(definition.provider_id):
                if not record.available:
                    continue
                if request.requested_tool_names and record.tool.name not in request.requested_tool_names:
                    continue
                candidates.append(ToolCandidate(
                    capability_id=request.capability_id,
                    operation_id=request.operation_id,
                    provider_id=definition.provider_id,
                    tool_name=record.tool.name,
                    priority=definition.priority,
                    quality_class=definition.quality_class,
                    latency_class=definition.latency_class,
                    record=record,
                ))
        result = tuple(sorted(candidates, key=ToolSelectionService.selection_key))
        self._publish(request, result)
        return result

    def _publish(self, request: ToolDiscoveryRequest, candidates: tuple[ToolCandidate, ...]) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(KernelEvent(
                event_type="ToolDiscoveryCompleted",
                source_component="tool_discovery",
                payload={"capability_id": request.capability_id, "operation_id": request.operation_id, "candidate_count": len(candidates)},
            ))


class ToolSelectionService:
    """Select a candidate using stable priority, quality, latency and IDs."""

    _quality_rank = {QualityClass.HIGH: 0, QualityClass.STANDARD: 1, QualityClass.BASIC: 2}
    _latency_rank = {LatencyClass.LOW: 0, LatencyClass.MEDIUM: 1, LatencyClass.HIGH: 2}

    def select(self, candidates: tuple[ToolCandidate, ...]) -> ToolCandidate:
        if not candidates:
            raise LookupError("No eligible MCP tool candidates")
        return min(candidates, key=self.selection_key)

    @classmethod
    def selection_key(cls, candidate: ToolCandidate) -> tuple[int, int, int, str, str]:
        return (-candidate.priority, cls._quality_rank[candidate.quality_class], cls._latency_rank[candidate.latency_class], candidate.provider_id, candidate.tool_name)
