"""Read live, scoped durable task states through the existing AURA MCP Gateway.

EventBus is only a refresh hint. Every authorized read queries real persisted
SQLite/PostgreSQL records with SQL-bound owner and LIMIT, no goal/result leaks.
"""
from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, asdict
from threading import RLock
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from aura_core.application.live_svg_chart import _principal
from aura_core.application.task_state_machine import TaskState, TaskStateMachine
from aura_core.application.postgresql_task_state_machine import PostgreSQLTaskStateMachine
from aura_core.kernel.capabilities import CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType
from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry
from aura_core.security.http_auth import authenticated_principal

_CAP = "visualization.tasks.read"
_PROVIDER = "visualization.tasks.local"
_TOOL = "read_live_task_states"
_SCOPE = "visualization/tasks/read-only"
_MAX_TASKS = 64
_TASK_ID = re.compile(r"\A[A-Za-z0-9_.:-]{1,128}\Z")
_EVENTS = ("TaskCreated", "TaskReady", "TaskStateChanged", "TaskCancellationRequested")


class LiveTaskDenied(PermissionError):
    """A real scoped Gateway ALLOW is required."""


class LiveTaskUnavailable(RuntimeError):
    """The persisted task projection is unavailable."""


@dataclass(frozen=True, slots=True)
class TaskPanelRow:
    task_id: str
    state: str
    updated_at: str
    revision: int


@dataclass(frozen=True, slots=True)
class LiveTaskEvidence:
    tasks: tuple[TaskPanelRow, ...]
    trust: str = "SCOPED_PERSISTED_TASK_STATE"
    read_only: bool = True


class LocalLiveTaskPanelMCP:
    def __init__(self, store: TaskStateMachine | PostgreSQLTaskStateMachine,
                 event_bus: EventBus) -> None:
        if not isinstance(store, (TaskStateMachine, PostgreSQLTaskStateMachine)):
            raise TypeError("Existing AURA task state machine required")
        if not isinstance(event_bus, EventBus):
            raise TypeError("Existing EventBus required")
        self._store = store
        self._lock = RLock()
        self._seen_changes = 0  # Not security evidence or authoritative state.
        self._unsubscribe = tuple(event_bus.subscribe(k, self._changed) for k in _EVENTS)

    def _changed(self, event: KernelEvent) -> None:
        if event.source_component == "aura.task_state_machine" and event.event_type in _EVENTS:
            with self._lock:
                self._seen_changes = (self._seen_changes + 1) % 1_000_000_000

    def close(self) -> None:
        for unsubscribe in self._unsubscribe:
            unsubscribe()

    async def list_tools(self) -> tuple[MCPTool, ...]:
        return (MCPTool(
            name=_TOOL, description="Read bounded per-principal persisted task states",
            input_schema={"type": "object", "properties": {}, "required": [],
                          "additionalProperties": False},
        ),)

    async def call_tool(self, name: str, arguments: dict | None = None) -> dict[str, object]:
        grant = current_dispatch()
        if (grant is None or grant.capability_id != _CAP or grant.tool_name != _TOOL
                or grant.risk_level != "low" or not grant.principal_id or name != _TOOL):
            raise LiveTaskDenied("Authorized MCP Gateway dispatch required")
        if arguments not in ({}, None):
            raise ValueError("No caller-controlled filters allowed")
        records = self._store.list_tasks_limited(
            principal_id=grant.principal_id, limit=_MAX_TASKS,
        )
        if inspect.isawaitable(records):
            records = await records
        if len(records) > _MAX_TASKS:
            raise LiveTaskUnavailable("Unbounded task store response")
        rows = []
        for record in records:
            if record.principal_id != grant.principal_id:
                raise LiveTaskUnavailable("Principal isolation violation")
            if not isinstance(record.task_id, str) or not _TASK_ID.fullmatch(record.task_id):
                continue
            rows.append({
                "task_id": record.task_id, "state": record.state.value,
                "updated_at": record.updated_at.isoformat(),
                "revision": record.revision, "principal_id": grant.principal_id,
            })
        return {"tasks": rows, "trust": "SCOPED_PERSISTED_TASK_STATE"}


def register_live_task_panel(*, services: ServiceRegistry, providers: ProviderRegistry,
                             capabilities: CapabilityRegistry, event_bus: EventBus,
                             task_state_machine: TaskStateMachine | PostgreSQLTaskStateMachine,
                             ) -> LocalLiveTaskPanelMCP:
    if not all((isinstance(services, ServiceRegistry), isinstance(providers, ProviderRegistry),
                isinstance(capabilities, CapabilityRegistry), isinstance(event_bus, EventBus))):
        raise TypeError("Existing Core registries/EventBus required")
    if any(x.definition.provider_id == _PROVIDER for x in providers.records()) or capabilities.providers(_CAP):
        raise ValueError("Duplicate task panel registration")
    backend = LocalLiveTaskPanelMCP(task_state_machine, event_bus)
    try:
        service = services.register(ServiceDefinition(
            name="aura-live-task-panel", version="1.0.0", provider="mcp",
            category=ServiceCategory.MCP,
        ), object())
        providers.register(ProviderDefinition(
            provider_id=_PROVIDER, name="Durable per-principal live tasks",
            version="1.0.0", service_id=service.service_id,
        ), backend)
        capabilities.register(CapabilityDefinition(
            capability_id=_CAP, name="Read persisted live task states",
            version="1.0.0", description="Read-only principal-scoped task lifecycle",
            provider_id=_PROVIDER, provider_type=ProviderType.MCP,
            category=CapabilityCategory.VISUALIZATION, risk_level="low", tool_name=_TOOL,
        ))
    except Exception:
        backend.close()
        raise
    return backend


class GovernedLiveTaskPanel:
    def __init__(self, gateway: MCPGateway, *, authenticated_principal_id: str) -> None:
        if not isinstance(gateway, MCPGateway):
            raise TypeError("Existing MCP Gateway required")
        self._gateway = gateway
        self.principal_id = _principal(authenticated_principal_id)

    async def read(self) -> LiveTaskEvidence:
        try:
            response = await self._gateway.invoke(MCPGatewayRequest(
                request_id="live-task-panel:" + str(uuid4()),
                principal_id=self.principal_id,
                capability_id=_CAP, operation_id=_CAP, resource_scope=_SCOPE,
                risk_level=RiskLevel.LOW, tool_name=_TOOL, arguments={},
            ))
        except Exception as exc:
            raise LiveTaskUnavailable("Task Gateway unavailable") from exc
        if response.decision is not AuthorizationDecision.ALLOW:
            raise LiveTaskDenied("Explicit task read policy required")
        data = response.result
        if (response.provider_id != _PROVIDER or not isinstance(data, dict)
                or data.get("status") == "failed"
                or data.get("trust") != "SCOPED_PERSISTED_TASK_STATE"):
            raise LiveTaskUnavailable("Invalid task projection")
        rows = data.get("tasks")
        if not isinstance(rows, list) or len(rows) > _MAX_TASKS:
            raise LiveTaskUnavailable("Unsafe task row count")
        output = []
        for row in rows:
            if (not isinstance(row, dict)
                    or set(row) != {"task_id", "state", "updated_at", "revision", "principal_id"}
                    or row["principal_id"] != self.principal_id
                    or not isinstance(row["task_id"], str) or not _TASK_ID.fullmatch(row["task_id"])
                    or row["state"] not in {s.value for s in TaskState}
                    or type(row["revision"]) is not int or not 0 <= row["revision"] <= 2**63 - 1
                    or not isinstance(row["updated_at"], str)
                    or not 10 <= len(row["updated_at"]) <= 64):
                raise LiveTaskUnavailable("Invalid or forged task row")
            output.append(TaskPanelRow(row["task_id"], row["state"],
                                       row["updated_at"], row["revision"]))
        return LiveTaskEvidence(tuple(output))


live_task_panel_router = APIRouter(tags=["governed-live-task-panel"])


@live_task_panel_router.get("/api/runtime/tasks")
async def read_live_tasks(request: Request,
                          principal_id: str = Depends(authenticated_principal)) -> JSONResponse:
    reader = getattr(request.app.state, "live_task_panel", None)
    if not isinstance(reader, GovernedLiveTaskPanel):
        raise HTTPException(status_code=503, detail="Live task panel not configured")
    if principal_id != reader.principal_id:
        raise HTTPException(status_code=403, detail="Task principal mismatch")
    try:
        result = await reader.read()
    except LiveTaskDenied as exc:
        raise HTTPException(status_code=403, detail="Task read unauthorized") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Task panel unavailable") from exc
    return JSONResponse(
        content={"tasks": [asdict(row) for row in result.tasks],
                 "read_only": True, "trust": result.trust},
        headers={"Cache-Control": "private, no-store",
                 "X-Content-Type-Options": "nosniff",
                 "Content-Security-Policy": "default-src 'none'; script-src 'none'"},
    )
