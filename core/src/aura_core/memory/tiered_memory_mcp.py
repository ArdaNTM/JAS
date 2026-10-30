"""Two-tier memory exposed only through MCP Gateway provider dispatch."""
from collections import OrderedDict
import inspect
from typing import Any
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.dispatch_context import current_dispatch

class TieredMemoryMCPProvider:
    provider_id = "aura.tiered-memory"
    def __init__(self, archival_store: Any, *, max_core_chars: int = 8000):
        if max_core_chars < 256:
            raise ValueError("max_core_chars must be >= 256")
        self._archival = archival_store
        self._max_core_chars = max_core_chars
        self._core = OrderedDict()

    async def list_tools(self):
        return (
            MCPTool("core_memory_append", "Append to bounded core memory", {
                "type":"object","properties":{"content":{"type":"string","minLength":1,"maxLength":4000}},
                "required":["content"],"additionalProperties":False}),
            MCPTool("core_memory_read", "Read principal core memory", {
                "type":"object","properties":{},"additionalProperties":False}),
            MCPTool("archival_memory_append", "Persist scoped archival memory", {
                "type":"object","properties":{"task_id":{"type":"string","minLength":1,"maxLength":200},
                "content":{"type":"string","minLength":1,"maxLength":20000}},
                "required":["task_id","content"],"additionalProperties":False}),
            MCPTool("archival_memory_search", "Search scoped archival memory", {
                "type":"object","properties":{"task_id":{"type":"string","minLength":1,"maxLength":200},
                "query":{"type":"string","minLength":1,"maxLength":2000},"limit":{"type":"integer"}},
                "required":["task_id","query"],"additionalProperties":False}),
        )

    async def call_tool(self, name: str, arguments=None):
        grant = current_dispatch()
        if grant is None or grant.tool_name != name:
            raise PermissionError("Memory operations must be dispatched by MCP Gateway")
        args = arguments or {}
        principal = grant.principal_id
        if name == "core_memory_append":
            updated = (self._core.get(principal, "") + "\n" + args["content"].strip()).strip()
            self._core[principal] = updated[-self._max_core_chars:]
            return {"stored": True, "characters": len(self._core[principal])}
        if name == "core_memory_read":
            return {"content": self._core.get(principal, ""), "untrusted": True}
        task_id = args["task_id"]
        if name == "archival_memory_append":
            record = self._archival.append(principal_id=principal, task_id=task_id,
                content=args["content"], source="mcp:archival_memory_append", metadata={"tier":"archival"})
            if inspect.isawaitable(record):
                record = await record
            return {"record_id":record.record_id,"stored":True}
        if name == "archival_memory_search":
            records = self._archival.recall(principal_id=principal, task_id=task_id,
                limit=max(1,min(int(args.get("limit",10)),50)))
            if inspect.isawaitable(records):
                records = await records
            query = args["query"].casefold()
            found = [{"record_id":r.record_id,"content":r.content,"created_at":r.created_at,"untrusted":True}
                     for r in records if query in r.content.casefold()]
            return {"records":found,"count":len(found)}
        raise KeyError("Unknown tiered-memory tool")
