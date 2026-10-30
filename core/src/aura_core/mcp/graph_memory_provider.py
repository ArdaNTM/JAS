"""Governed principal-scoped GraphRAG MCP adapter; backend selected by composition."""
from __future__ import annotations

import inspect
from collections import defaultdict
from threading import RLock
from uuid import uuid4

from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.mcp_provider import MCPTool


class GraphMemoryMCPProvider:
    provider_id = "aura.graph-memory"

    def __init__(self, store=None, *, max_facts_per_principal: int = 1000):
        if max_facts_per_principal < 1:
            raise ValueError("Graph capacity must be positive")
        self._store = store
        self._facts = defaultdict(dict) if store is None else None
        self._max = max_facts_per_principal
        self._lock = RLock()

    async def list_tools(self):
        fields = {
            "subject": {"type": "string", "minLength": 1, "maxLength": 200},
            "predicate": {"type": "string", "minLength": 1, "maxLength": 200},
            "object": {"type": "string", "minLength": 1, "maxLength": 2000},
        }
        return (
            MCPTool("graph_memory_insert", "Insert principal-scoped graph relation",
                    {"type": "object", "properties": fields,
                     "required": list(fields), "additionalProperties": False}),
            MCPTool("graph_memory_query", "Query principal-scoped relations up to 2 hops",
                    {"type": "object", "properties": {
                        "subject": fields["subject"], "limit": {"type": "integer"},
                        "depth": {"type": "integer"}},
                     "required": ["subject"], "additionalProperties": False}),
        )

    async def call_tool(self, name, arguments=None):
        grant = current_dispatch()
        expected = {
            "graph_memory_insert": "memory.graph.insert",
            "graph_memory_query": "memory.graph.query",
        }
        if (grant is None or name not in expected or grant.tool_name != name
                or grant.capability_id != expected[name]):
            raise PermissionError("Graph operations require authorized MCP Gateway dispatch")

        args = arguments or {}
        principal = grant.principal_id
        if name == "graph_memory_insert":
            data = {key: args[key] for key in ("subject", "predicate", "object")}
            if self._store is not None:
                fact_id = self._store.insert(principal_id=principal, **data)
                if inspect.isawaitable(fact_id):
                    fact_id = await fact_id
                return {"fact_id": fact_id, "stored": True}
            with self._lock:
                assert self._facts is not None
                facts = self._facts[principal]
                if len(facts) >= self._max:
                    raise ValueError("Graph capacity exceeded")
                fact_id = str(uuid4())
                facts[fact_id] = data
            return {"fact_id": fact_id, "stored": True}

        limit = args.get("limit", 20)
        depth = args.get("depth", 1)
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("limit must be in 1..50")
        if type(depth) is not int or depth not in (1, 2):
            raise ValueError("depth must be 1 or 2")
        if self._store is not None:
            records = self._store.query(
                principal_id=principal, subject=args["subject"], limit=limit, depth=depth)
            if inspect.isawaitable(records):
                records = await records
            return {"facts": records, "count": len(records)}
        with self._lock:
            assert self._facts is not None
            results, frontier, seen = [], [args["subject"]], {args["subject"]}
            for _ in range(depth):
                next_frontier = []
                for subject in frontier:
                    for key, value in self._facts[principal].items():
                        if value["subject"] != subject:
                            continue
                        results.append({"fact_id": key, **value, "untrusted": True})
                        if value["object"] not in seen:
                            seen.add(value["object"])
                            next_frontier.append(value["object"])
                        if len(results) >= limit:
                            return {"facts": results, "count": len(results)}
                frontier = next_frontier
        return {"facts": results, "count": len(results)}
