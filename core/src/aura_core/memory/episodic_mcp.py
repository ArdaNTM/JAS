"""Opt-in, Gateway-scoped SQLite episodic-memory MCP provider (#1/#99).

This adds no permission policy, Owner identity, network endpoint or self-activation.
Recalled text is *untrusted data*, not an instruction or a source of tool grants.
"""
from __future__ import annotations

import asyncio
from typing import Any

from aura_core.application.episodic_memory import EpisodicMemoryStore
from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityDefinition, ProviderType,
)
from aura_core.kernel.services import ServiceCategory, ServiceDefinition
from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.provider import ProviderDefinition

CAPABILITIES = {
    "remember": "aura.memory.episodic.write",
    "recall": "aura.memory.episodic.read",
    "forget": "aura.memory.episodic.delete",
}
KINDS = ["preference", "fact", "episode", "goal", "lesson", "reasoning"]


class ScopedEpisodicMemoryMCP:
    provider_id = "aura.scoped-episodic-memory"
    requires_approval = False  # The high-risk delete tool independently requires it.

    def __init__(self, store: EpisodicMemoryStore) -> None:
        if not isinstance(store, EpisodicMemoryStore):
            raise TypeError("Existing durable EpisodicMemoryStore is required")
        self.store = store

    async def list_tools(self) -> tuple[MCPTool, ...]:
        return (
            MCPTool(
                "remember", "Persist bounded user-provided data scoped to current principal",
                {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": KINDS},
                        "content": {"type": "string", "minLength": 1, "maxLength": 8000},
                    },
                    "required": ["kind", "content"],
                    "additionalProperties": False,
                },
            ),
            MCPTool(
                "recall", "Read only current principal's untrusted durable memory",
                {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "maxLength": 200},
                        "limit": {"type": "integer"},
                    },
                    "additionalProperties": False,
                },
            ),
            MCPTool(
                "forget", "Single-use approval-bound delete of scoped memory",
                {
                    "type": "object",
                    "properties": {
                        "memory_id": {"type": "string", "minLength": 1, "maxLength": 128},
                    },
                    "required": ["memory_id"],
                    "additionalProperties": False,
                },
            ),
        )

    async def call_tool(self, name: str, arguments: Any = None) -> dict[str, Any]:
        grant = current_dispatch()
        expected = CAPABILITIES.get(name)
        if (
            grant is None
            or expected is None
            or grant.capability_id != expected
            or grant.tool_name != name
            or not isinstance(grant.principal_id, str)
            or not grant.principal_id.strip()
        ):
            raise PermissionError("Memory requires exact MCP Gateway dispatch grant")
        if name == "forget" and (
            grant.risk_level not in {"high", "critical"} or
            not grant.approval_consumed
        ):
            raise PermissionError("Memory deletion requires consumed high-risk approval")
        if name != "forget" and grant.risk_level not in {"low", "medium", "high", "critical"}:
            raise PermissionError("Invalid memory tool risk level")
        args = arguments if isinstance(arguments, dict) else {}
        tools = {item.name: item.input_schema for item in await self.list_tools()}
        # Defence in depth for accidental direct dispatch from other adapters.
        from aura_core.mcp.gateway import _validate_json_schema
        _validate_json_schema(args, tools[name])
        principal_id = grant.principal_id

        if name == "remember":
            record = await asyncio.to_thread(
                self.store.remember,
                principal_id=principal_id, kind=args["kind"], content=args["content"],
            )
            return {**record.to_dict(), "untrusted": True}
        if name == "recall":
            records = await asyncio.to_thread(
                self.store.recall,
                principal_id=principal_id,
                query=args.get("query", ""),
                limit=args.get("limit", 20),
            )
            return {"records": [
                {**record.to_dict(), "untrusted": True}
                for record in records
            ]}
        deleted = await asyncio.to_thread(
            self.store.forget, principal_id=principal_id,
            memory_id=args["memory_id"],
        )
        return {"deleted": deleted}


def register_scoped_memory(kernel: Any, provider: ScopedEpisodicMemoryMCP) -> None:
    """Explicit registration only; local policies remain default-DENY.

    Must be called by a separately reviewed bootstrap. Deliberately does not
    mutate main.py or initialize an implicit listening network endpoint.
    """
    if (
        kernel.service_registry is None or
        kernel.provider_registry is None or
        kernel.capability_registry is None
    ):
        raise RuntimeError("AURA Kernel must be bootstrapped first")
    service = ServiceDefinition(
        name="scoped_episodic_memory_mcp", version="1.0.0", provider="aura",
        category=ServiceCategory.MCP,
        capabilities=frozenset(CAPABILITIES.values()),
        tags=frozenset({"memory", "sqlite", "mcp", "gateway-scoped"}),
    )
    kernel.service_registry.register(service, provider)
    kernel.provider_registry.register(ProviderDefinition(
        provider_id=provider.provider_id,
        name="Scoped SQLite Episodic Memory",
        version="1.0.0", service_id=service.service_id,
        description="Durable memory, fully governed by existing MCP Gateway",
    ), provider)
    for name, capability_id in CAPABILITIES.items():
        kernel.capability_registry.register(CapabilityDefinition(
            capability_id=capability_id,
            name=f"Scoped memory {name}",
            version="1.0.0",
            description="Principal-scoped, untrusted episodic memory data",
            provider_id=provider.provider_id, provider_type=ProviderType.MCP,
            category=CapabilityCategory.MEMORY,
            tool_name=name,
            risk_level="high" if name == "forget" else "low",
            required_permissions=frozenset({capability_id}),
        ))
