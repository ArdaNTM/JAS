"""Principal-scoped GraphRAG storage exposed only under the existing MCP Gateway.

The actual store is the existing SQLiteGraphStore/PostgreSQLGraphStore.
No new policy, Owner identity, gateway bypass or default network listener.
"""
from __future__ import annotations

from typing import Any

from aura_core.kernel.capabilities import CapabilityCategory, CapabilityDefinition, ProviderType
from aura_core.kernel.services import ServiceCategory, ServiceDefinition
from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.provider import ProviderDefinition
from aura_core.memory.graph_store import SQLiteGraphStore, PostgreSQLGraphStore

CAPABILITIES = {
    "graph_insert": "aura.memory.graph.insert",
    "graph_query": "aura.memory.graph.query",
    "graph_delete": "aura.memory.graph.delete",
    "graph_soft_delete": "aura.memory.graph.soft_delete",
    "graph_restore": "aura.memory.graph.restore",
}


class GovernedGraphMCP:
    provider_id = "aura.governed-graph"

    def __init__(self, store: SQLiteGraphStore | PostgreSQLGraphStore) -> None:
        if not isinstance(store, (SQLiteGraphStore, PostgreSQLGraphStore)):
            raise TypeError("Existing graph storage engine required")
        self.store = store

    async def list_tools(self) -> tuple[MCPTool, ...]:
        return (
            MCPTool("graph_insert", "Persist owner-scoped untrusted graph fact", {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "minLength": 1, "maxLength": 200},
                    "predicate": {"type": "string", "minLength": 1, "maxLength": 200},
                    "object": {"type": "string", "minLength": 1, "maxLength": 2000},
                },
                "required": ["subject", "predicate", "object"],
                "additionalProperties": False,
            }),
            MCPTool("graph_query", "Read bounded principal-scoped facts", {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "minLength": 1, "maxLength": 200},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "depth": {"type": "integer", "minimum": 1, "maximum": 2},
                },
                "required": ["subject"], "additionalProperties": False,
            }),
            MCPTool("graph_soft_delete", "Tombstone one fact with consumed Owner approval", {
                "type": "object", "properties": {
                    "fact_id": {"type": "string", "minLength": 1, "maxLength": 64}
                }, "required": ["fact_id"], "additionalProperties": False,
            }),
            MCPTool("graph_restore", "Restore one fact with consumed Owner approval", {
                "type": "object", "properties": {
                    "fact_id": {"type": "string", "minLength": 1, "maxLength": 64}
                }, "required": ["fact_id"], "additionalProperties": False,
            }),
            MCPTool("graph_delete", "Delete one fact with consumed Owner approval", {
                "type": "object",
                "properties": {
                    "fact_id": {"type": "string", "minLength": 1, "maxLength": 64},
                },
                "required": ["fact_id"], "additionalProperties": False,
            }),
        )

    async def call_tool(self, name: str, arguments: Any = None) -> dict[str, Any]:
        grant = current_dispatch()
        if (grant is None or name not in CAPABILITIES or
            grant.capability_id != CAPABILITIES[name] or grant.tool_name != name or
            type(grant.principal_id) is not str or not grant.principal_id.strip()):
            raise PermissionError("Exact MCPGateway dispatch grant is mandatory")
        if name in {"graph_delete", "graph_soft_delete", "graph_restore"} and (
            not grant.approval_consumed or grant.risk_level not in {"high", "critical"}
        ):
            raise PermissionError("Graph deletion requires consumed HIGH-risk approval")
        from aura_core.mcp.gateway import _validate_json_schema
        schemas = {tool.name: tool.input_schema for tool in await self.list_tools()}
        args = arguments if isinstance(arguments, dict) else {}
        _validate_json_schema(args, schemas[name])
        principal = grant.principal_id  # never trust JSON to choose an owner
        if name == "graph_insert":
            fact_id = await self.store.insert(
                principal_id=principal, subject=args["subject"],
                predicate=args["predicate"], object=args["object"])
            return {"fact_id": fact_id, "untrusted": True}
        if name == "graph_query":
            facts = await self.store.query(
                principal_id=principal, subject=args["subject"],
                limit=args.get("limit", 20), depth=args.get("depth", 1))
            return {"facts": facts, "untrusted": True}
        if name == "graph_soft_delete":
            changed = await self.store.soft_delete_fact(
                principal_id=principal, fact_id=args["fact_id"], confirmed=True)
            return {"soft_deleted": changed, "audited": changed}
        if name == "graph_restore":
            changed = await self.store.restore_fact(
                principal_id=principal, fact_id=args["fact_id"], confirmed=True)
            return {"restored": changed, "audited": changed}
        deleted = await self.store.delete_fact(
            principal_id=principal, fact_id=args["fact_id"], confirmed=True)
        return {"deleted": deleted}


def register_governed_graph(kernel: Any, provider: GovernedGraphMCP) -> None:
    """Registry-only opt-in; default PermissionEngine denies all new capabilities."""
    if (kernel.service_registry is None or kernel.provider_registry is None or
        kernel.capability_registry is None):
        raise RuntimeError("Kernel must be bootstrapped")
    service = ServiceDefinition(
        name="governed_graph", version="1.0.0", provider="aura",
        category=ServiceCategory.MCP,
        capabilities=frozenset(CAPABILITIES.values()),
    )
    kernel.service_registry.register(service, provider)
    kernel.provider_registry.register(ProviderDefinition(
        provider_id=provider.provider_id, name="Principal scoped SQLite/PostgreSQL graph",
        version="1.0.0", service_id=service.service_id), provider)
    for name, cap in CAPABILITIES.items():
        kernel.capability_registry.register(CapabilityDefinition(
            capability_id=cap, name="Graph " + name, version="1.0.0",
            description="Owner-scoped graph fact data, never a policy source",
            provider_id=provider.provider_id, provider_type=ProviderType.MCP,
            category=CapabilityCategory.MEMORY, tool_name=name,
            risk_level="high" if name in {"graph_delete", "graph_soft_delete", "graph_restore"} else "low",
        ))
