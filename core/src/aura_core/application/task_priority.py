"""Durable task priority overlay for existing TaskStateMachine, with no new scheduler.

Task owners and tool callers are resolved by the trusted MCP Gateway, never
from model-supplied JSON. TaskStateMachine remains authoritative for task status.
"""
from __future__ import annotations

import asyncio
import sqlite3
import threading
from pathlib import Path
from typing import Any

from aura_core.application.task_state_machine import TaskStateMachine
from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.kernel.capabilities import CapabilityDefinition, CapabilityCategory, ProviderType
from aura_core.kernel.services import ServiceDefinition, ServiceCategory
from aura_core.mcp.provider import ProviderDefinition

TASK_PRIORITY_CAPS = {
    "task_priority_get": "aura.task.priority.read",
    "task_priority_set": "aura.task.priority.write",
}


class TaskPriorityLedger:
    """Optimistically versioned SQLite task priorities scoped by real task owner."""

    def __init__(self, state_machine: TaskStateMachine, database_path: str | Path) -> None:
        if not isinstance(state_machine, TaskStateMachine):
            raise TypeError("Existing task state machine required")
        self._tasks = state_machine
        self._path = str(database_path)
        if self._path != ":memory:":
            Path(self._path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self._path, timeout=5, isolation_level=None,
                                   check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        if self._path != ":memory:":
            self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("""CREATE TABLE IF NOT EXISTS task_priorities (
            principal_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            priority INTEGER NOT NULL CHECK(priority BETWEEN 0 AND 5),
            revision INTEGER NOT NULL CHECK(revision > 0),
            PRIMARY KEY(principal_id, task_id)
        )""")

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def get(self, *, principal_id: str, task_id: str) -> dict[str, Any]:
        # Must not expose another principal's task through an unscoped lookup.
        self._tasks.get(task_id, principal_id=principal_id)
        with self._lock:
            record = self._db.execute("""SELECT priority, revision FROM task_priorities
                WHERE principal_id=? AND task_id=?""", (principal_id, task_id)).fetchone()
        return {
            "task_id": task_id, "priority": record["priority"] if record else 0,
            "revision": record["revision"] if record else 0,
            "state_authoritative": True, "untrusted": False,
        }

    def set(self, *, principal_id: str, task_id: str,
            priority: int, expected_revision: int) -> dict[str, Any]:
        if type(priority) is not int or not 0 <= priority <= 5:
            raise ValueError("priority must be int 0..5")
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("revision must be nonnegative integer")
        self._tasks.get(task_id, principal_id=principal_id)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                record = self._db.execute(
                    "SELECT revision FROM task_priorities WHERE principal_id=? AND task_id=?",
                    (principal_id, task_id)).fetchone()
                current = record["revision"] if record else 0
                if current != expected_revision:
                    raise ValueError("task priority revision conflict")
                self._db.execute("""INSERT INTO task_priorities(principal_id,task_id,priority,revision)
                    VALUES(?,?,?,?)
                    ON CONFLICT(principal_id, task_id) DO UPDATE SET
                    priority=excluded.priority, revision=excluded.revision""",
                    (principal_id, task_id, priority, current + 1))
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        return {"task_id": task_id, "priority": priority,
                "revision": current + 1, "persisted": True}


class GovernedTaskPriorityMCP:
    """Opt-in Gateway-only adapter. No default authorization policies added."""

    provider_id = "aura.governed-task-priority"

    def __init__(self, ledger: TaskPriorityLedger) -> None:
        if not isinstance(ledger, TaskPriorityLedger):
            raise TypeError("TaskPriorityLedger required")
        self.ledger = ledger

    async def list_tools(self) -> tuple[MCPTool, ...]:
        props = {"task_id": {"type": "string", "minLength": 1, "maxLength": 128}}
        return (
            MCPTool("task_priority_get", "Get persisted scoped priority", {
                "type": "object", "properties": props,
                "required": ["task_id"], "additionalProperties": False,
            }),
            MCPTool("task_priority_set", "Set CAS-protected scoped priority", {
                "type": "object",
                "properties": {
                    **props,
                    "priority": {"type": "integer", "minimum": 0, "maximum": 5},
                    "expected_revision": {"type": "integer", "minimum": 0},
                },
                "required": ["task_id", "priority", "expected_revision"],
                "additionalProperties": False,
            }),
        )

    async def call_tool(self, name: str, arguments: Any = None) -> dict[str, Any]:
        grant = current_dispatch()
        if (grant is None or name not in TASK_PRIORITY_CAPS or
            grant.capability_id != TASK_PRIORITY_CAPS[name] or grant.tool_name != name or
            type(grant.principal_id) is not str or not grant.principal_id):
            raise PermissionError("Task priority requires exact Gateway grant")
        from aura_core.mcp.gateway import _validate_json_schema
        args = arguments if isinstance(arguments, dict) else {}
        schemas = {t.name: t.input_schema for t in await self.list_tools()}
        _validate_json_schema(args, schemas[name])
        if name == "task_priority_get":
            return await asyncio.to_thread(self.ledger.get,
                principal_id=grant.principal_id, task_id=args["task_id"])
        return await asyncio.to_thread(self.ledger.set,
            principal_id=grant.principal_id, task_id=args["task_id"],
            priority=args["priority"], expected_revision=args["expected_revision"])


def register_governed_task_priority(kernel: Any, provider: GovernedTaskPriorityMCP) -> None:
    if (kernel.service_registry is None or kernel.provider_registry is None or
        kernel.capability_registry is None):
        raise RuntimeError("Kernel must be bootstrapped")
    service = ServiceDefinition(
        name="governed_task_priority", version="1.0.0", provider="aura",
        category=ServiceCategory.MCP,
        capabilities=frozenset(TASK_PRIORITY_CAPS.values()))
    kernel.service_registry.register(service, provider)
    kernel.provider_registry.register(ProviderDefinition(
        provider_id=provider.provider_id, name="Versioned SQLite Task Priorities",
        version="1.0.0", service_id=service.service_id), provider)
    for name, cap in TASK_PRIORITY_CAPS.items():
        kernel.capability_registry.register(CapabilityDefinition(
            capability_id=cap, name="Task priority " + name, version="1.0.0",
            description="Versioned, owner-scoped task data",
            provider_id=provider.provider_id, provider_type=ProviderType.MCP,
            category=CapabilityCategory.PLANNING, tool_name=name,
            risk_level="low" if name.endswith("get") else "medium"))
