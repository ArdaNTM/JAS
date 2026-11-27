"""Read-only, principal-scoped daily briefing over existing durable task stores."""
from __future__ import annotations

import asyncio
from collections import Counter
from datetime import UTC, datetime

from aura_core.application.task_state_machine import TaskState, TERMINAL_STATES
from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.mcp_provider import MCPTool

BRIEFING_CAP = "jarvis.briefing.read"
BRIEFING_TOOL = "briefing_read"
BRIEFING_SCOPE = "jarvis/briefing/read-only"
BRIEFING_PROVIDER = "aura.jarvis-briefing"


class BriefingService:
    def __init__(self, tasks, workflows, memory) -> None:
        self.tasks, self.workflows, self.memory = tasks, workflows, memory

    async def list_tools(self):
        return (MCPTool(BRIEFING_TOOL, "Read today's scoped task priorities and warnings",
                        {"type": "object", "properties": {}, "additionalProperties": False}),)

    async def call_tool(self, name, arguments=None):
        grant = current_dispatch()
        if (grant is None or grant.capability_id != BRIEFING_CAP or grant.tool_name != BRIEFING_TOOL
                or name != BRIEFING_TOOL or grant.risk_level != "low" or not grant.principal_id):
            raise PermissionError("Authorized briefing Gateway dispatch required")
        if arguments not in ({}, None):
            raise ValueError("Briefing accepts no caller-supplied scope")
        return await asyncio.to_thread(self._read, grant.principal_id)

    def _read(self, principal: str) -> dict:
        records = self.tasks.list_tasks_limited(principal_id=principal, limit=64)
        if len(records) > 64 or any(r.principal_id != principal for r in records):
            raise PermissionError("Unsafe task store projection")
        incomplete = [r for r in records if r.state not in TERMINAL_STATES]
        dependents = Counter(dep for record in incomplete for dep in record.dependencies)
        now = datetime.now(UTC)
        plan, alerts = [], []
        # Read only actual state transitions; model claims never determine readiness.
        for record in records:
            if record.state in {TaskState.SUCCEEDED, TaskState.CANCELLED}:
                continue
            unresolved = []
            for dependency in record.dependencies:
                try:
                    state = self.tasks.get(dependency, principal_id=principal).state
                except KeyError:
                    state = None
                if state != TaskState.SUCCEEDED:
                    unresolved.append(dependency)
            overdue = record.deadline is not None and record.deadline <= now
            row = {
                "task_id": record.task_id,
                "goal": record.goal[:300],
                "state": record.state.value,
                "unresolved_dependencies": unresolved[:20],
                "deadline": record.deadline.isoformat() if record.deadline else None,
                "unblocks": dependents[record.task_id],
                "memory_state": None,
                "workflow_state": None,
                "goal_progress": None,
                "untrusted": True,
            }
            checkpoint = self.memory.store.load_checkpoint(principal_id=principal, task_id=record.task_id)
            if checkpoint and checkpoint.get("state") in {"running", "succeeded", "failed", "cancelled"}:
                row["memory_state"] = checkpoint["state"]
            workflow = self.workflows.get(record.task_id)
            if workflow is not None and workflow.principal_id == principal and workflow.task_id == record.task_id:
                row["workflow_state"] = workflow.status.value
            try:
                progress = self.tasks.goal_progress(principal_id=principal, goal=record.goal)
                row["goal_progress"] = progress["percent_complete"]
            except ValueError:
                # The goal may exceed the bounded authoritative projection.
                pass
            if overdue or unresolved or record.state in {TaskState.FAILED, TaskState.BLOCKED, TaskState.TIMED_OUT}:
                alerts.append({**row, "reason": "overdue" if overdue else
                               "dependency" if unresolved else record.state.value})
            if record.state not in TERMINAL_STATES and not unresolved and not record.cancellation_requested:
                plan.append(row)
        plan.sort(key=lambda r: (r["deadline"] is None, r["deadline"] or "",
                                -r["unblocks"], r["state"] != "running", r["task_id"]))
        alerts.sort(key=lambda r: (r["reason"] != "overdue", -r["unblocks"], r["task_id"]))
        return {
            "title": "Günün Planı", "alerts_title": "Kritik Uyarılar",
            "plan": plan[:12], "alerts": alerts[:12],
            "scanned": len(records), "bounded": True, "read_only": True, "untrusted": True,
        }
