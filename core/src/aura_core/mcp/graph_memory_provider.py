"""Principal-isolated, bounded knowledge graph MCP provider (in-memory baseline)."""
from __future__ import annotations

from collections import defaultdict
from threading import RLock
from uuid import uuid4

from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.mcp_provider import MCPTool


class GraphMemoryMCPProvider:
    provider_id = "aura.graph-memory"

    def __init__(self, *, max_facts_per_principal: int = 1000):
        if max_facts_per_principal < 1:
            raise ValueError("Graph capacity must be positive")
        self._facts = defaultdict(dict)
        self._max = max_facts_per_principal
        self._lock = RLock()

    async def list_tools(self):
        fields = {
            "subject": {"type": "string", "minLength": 1, "maxLength": 200},
            "predicate": {"type": "string", "minLength": 1, "maxLength": 200},
            "object": {"type": "string", "minLength": 1, "maxLength": 2000},
        }
        return (
            MCPTool("graph_memory_insert", "Insert an untrusted principal-scoped fact",
                    {"type": "object", "properties": fields,
                     "required": list(fields), "additionalProperties": False}),
            MCPTool("graph_memory_query", "Query principal-scoped facts",
                    {"type": "object", "properties": {"subject": fields["subject"],
                       "limit": {"type": "integer"}},
                     "required": ["subject"], "additionalProperties": False}),
        )

    async def call_tool(self, name, arguments=None):
        grant = current_dispatch()
        expected = {
            "graph_memory_insert": "memory.graph.insert",
            "graph_memory_query": "memory.graph.query",
        }
        if grant is None or name not in expected or grant.tool_name != name or grant.capability_id != expected[name]:
            raise PermissionError("Graph operations require authorized MCP Gateway dispatch")
        args = arguments or {}
        principal = grant.principal_id
        with self._lock:
            facts = self._facts[principal]
            if name == "graph_memory_insert":
                if len(facts) >= self._max:
                    raise ValueError("Graph capacity exceeded")
                fact_id = str(uuid4())
                facts[fact_id] = {key: args[key] for key in ("subject", "predicate", "object")}
                return {"fact_id": fact_id, "stored": True}
            limit = max(1, min(int(args.get("limit", 20)), 50))
            results = [{"fact_id": key, **value, "untrusted": True}
                       for key, value in facts.items() if value["subject"] == args["subject"]]
            return {"facts": results[:limit], "count": min(len(results), limit)}
