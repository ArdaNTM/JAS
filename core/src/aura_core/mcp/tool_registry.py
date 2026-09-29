from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import RLock
from typing import Iterable

from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.mcp.mcp_provider import MCPTool


@dataclass(frozen=True, slots=True)
class MCPToolRecord:
    provider_id: str
    tool: MCPTool
    discovered_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )
    available: bool = True

    def __post_init__(self) -> None:
        if not self.provider_id:
            raise ValueError("Tool provider_id is required")

        if not self.tool.name:
            raise ValueError("Tool name is required")


class MCPToolRegistry:
    """Authoritative registry for tools exposed by MCP providers."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._records: dict[tuple[str, str], MCPToolRecord] = {}
        self._lock = RLock()

    def register(
        self,
        provider_id: str,
        tool: MCPTool,
    ) -> MCPToolRecord:
        record = MCPToolRecord(
            provider_id=provider_id,
            tool=tool,
        )
        key = provider_id, tool.name

        with self._lock:
            if key in self._records:
                raise ValueError(
                    f"MCP tool is already registered: "
                    f"{provider_id}/{tool.name}"
                )

            self._records[key] = record

        self._publish("MCPToolRegistered", record)
        return record

    def register_many(
        self,
        provider_id: str,
        tools: Iterable[MCPTool],
    ) -> tuple[MCPToolRecord, ...]:
        tools = tuple(tools)

        with self._lock:
            keys = [
                (provider_id, tool.name)
                for tool in tools
            ]

            duplicates = [
                key
                for key in keys
                if key in self._records
            ]

            if duplicates:
                provider, name = duplicates[0]
                raise ValueError(
                    f"MCP tool is already registered: "
                    f"{provider}/{name}"
                )

            records = tuple(
                MCPToolRecord(
                    provider_id=provider_id,
                    tool=tool,
                )
                for tool in tools
            )

            for record in records:
                self._records[
                    (record.provider_id, record.tool.name)
                ] = record

        for record in records:
            self._publish("MCPToolRegistered", record)

        return records

    def resolve(
        self,
        provider_id: str,
        tool_name: str,
    ) -> MCPToolRecord:
        key = provider_id, tool_name

        with self._lock:
            try:
                record = self._records[key]
            except KeyError as exc:
                raise KeyError(
                    f"Unknown MCP tool: "
                    f"{provider_id}/{tool_name}"
                ) from exc

            if not record.available:
                raise LookupError(
                    f"MCP tool is unavailable: "
                    f"{provider_id}/{tool_name}"
                )

            return record

    def find(
        self,
        tool_name: str,
    ) -> tuple[MCPToolRecord, ...]:
        with self._lock:
            return tuple(
                sorted(
                    (
                        record
                        for record in self._records.values()
                        if record.tool.name == tool_name
                        and record.available
                    ),
                    key=lambda record: record.provider_id,
                )
            )

    def tools_for_provider(
        self,
        provider_id: str,
    ) -> tuple[MCPToolRecord, ...]:
        with self._lock:
            return tuple(
                sorted(
                    (
                        record
                        for record in self._records.values()
                        if record.provider_id == provider_id
                    ),
                    key=lambda record: record.tool.name,
                )
            )

    def records(self) -> tuple[MCPToolRecord, ...]:
        with self._lock:
            return tuple(
                sorted(
                    self._records.values(),
                    key=lambda record: (
                        record.provider_id,
                        record.tool.name,
                    ),
                )
            )

    def unregister(
        self,
        provider_id: str,
        tool_name: str,
    ) -> MCPToolRecord:
        key = provider_id, tool_name

        with self._lock:
            try:
                record = self._records.pop(key)
            except KeyError as exc:
                raise KeyError(
                    f"Unknown MCP tool: "
                    f"{provider_id}/{tool_name}"
                ) from exc

        retired = MCPToolRecord(
            provider_id=record.provider_id,
            tool=record.tool,
            discovered_at=record.discovered_at,
            available=False,
        )

        self._publish("MCPToolRemoved", retired)
        return retired

    def unregister_provider(
        self,
        provider_id: str,
    ) -> tuple[MCPToolRecord, ...]:
        with self._lock:
            records = tuple(
                record
                for record in self._records.values()
                if record.provider_id == provider_id
            )

            for record in records:
                self._records.pop(
                    (record.provider_id, record.tool.name),
                    None,
                )

        retired = tuple(
            MCPToolRecord(
                provider_id=record.provider_id,
                tool=record.tool,
                discovered_at=record.discovered_at,
                available=False,
            )
            for record in records
        )

        for record in retired:
            self._publish("MCPToolRemoved", record)

        return retired

    def _publish(
        self,
        event_type: str,
        record: MCPToolRecord,
    ) -> None:
        if self._event_bus is None:
            return

        self._event_bus.publish(
            KernelEvent(
                event_type=event_type,
                source_component="mcp_tool_registry",
                payload={
                    "provider_id": record.provider_id,
                    "tool_name": record.tool.name,
                    "available": record.available,
                },
            )
        )
