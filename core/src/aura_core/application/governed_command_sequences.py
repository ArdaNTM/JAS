"""Durable, explicitly stepped local command workflows on AURA TaskStateMachine.

Steps are stored as owner-bound HMAC-sealed tasks with dependency edges in the
existing SQLite/PostgreSQL TaskStateMachine. No background action or implicit
approval. Every step requires its own original terminal Gateway decision and
consumed one-shot Owner receipt before any Docker execution.
"""
from __future__ import annotations

import hashlib
import hmac
import inspect
import re
from dataclasses import dataclass
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from aura_core.application.task_state_machine import TaskState, TaskStateMachine
from aura_core.application.postgresql_task_state_machine import PostgreSQLTaskStateMachine
from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType,
)
from aura_core.kernel.services import ServiceDefinition, ServiceCategory, ServiceRegistry
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry
from aura_core.providers.docker_terminal_mcp import (
    GovernedDockerTerminal, TerminalDenied, TerminalUnavailable,
)
from aura_core.security.http_auth import authenticated_principal

_PROVIDER = "workflow.commands.local"
_CREATE = "workflow.commands.plan"
_ADVANCE = "workflow.commands.advance"
_CATALOG = re.compile(r"\A[a-z][a-z0-9_-]{0,47}\Z")
_UUID = re.compile(r"\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
_MAX_STEPS = 6
_MARKER = "aura.command-sequence.v1"


class CommandSequenceDenied(PermissionError):
    """Explicit Gateway and per-step Owner authority absent."""


class CommandSequenceUnavailable(RuntimeError):
    """Durable step execution unavailable; do not expose internals."""


async def _await(value):
    return await value if inspect.isawaitable(value) else value


@dataclass(frozen=True, slots=True)
class SequenceEvidence:
    task_ids: tuple[str, ...] = ()
    task_id: str | None = None
    command_id: str | None = None
    state: str = "created"
    approval_id: str | None = None
    trust: str = "PERSISTED_OWNER_SCOPED_SEQUENCE"


class LocalCommandSequenceMCP:
    """Authenticated owner-only manual transition coordinator, no daemon."""

    def __init__(self, *, tasks: TaskStateMachine | PostgreSQLTaskStateMachine,
                 terminal: GovernedDockerTerminal, hmac_key: bytes,
                 allowed_command_ids: tuple[str, ...], event_bus: EventBus) -> None:
        if not isinstance(tasks, (TaskStateMachine, PostgreSQLTaskStateMachine)):
            raise TypeError("Existing persistent TaskStateMachine required")
        if not isinstance(terminal, GovernedDockerTerminal) or not isinstance(event_bus, EventBus):
            raise TypeError("Existing Gateway terminal and EventBus required")
        if type(hmac_key) is not bytes or len(hmac_key) < 32:
            raise ValueError("Owner-controlled sequence HMAC key must be >=32 bytes")
        if (type(allowed_command_ids) is not tuple or not 1 <= len(allowed_command_ids) <= 12
                or len(set(allowed_command_ids)) != len(allowed_command_ids)
                or any(type(x) is not str or not _CATALOG.fullmatch(x) for x in allowed_command_ids)):
            raise ValueError("Trusted finite command catalog required")
        self._tasks = tasks
        self._terminal = terminal
        self._key = hmac_key
        self._catalog = frozenset(allowed_command_ids)
        self._bus = event_bus

    def _seal(self, principal: str, task_id: str, command: str,
              dependency: str | None) -> str:
        raw = "\n".join((principal, task_id, command, dependency or "-")).encode("utf-8")
        return hmac.new(self._key, raw, hashlib.sha256).hexdigest()

    async def list_tools(self) -> tuple[MCPTool, ...]:
        return (
            MCPTool(name="plan_terminal_sequence",
                    description="Persist a bounded, explicitly stepped terminal workflow",
                    input_schema={"type": "object", "properties": {
                        "commands": {"type": "array", "minItems": 1, "maxItems": _MAX_STEPS,
                                     "items": {"type": "string", "minLength": 1, "maxLength": 48}},
                    }, "required": ["commands"], "additionalProperties": False}),
            MCPTool(name="advance_terminal_sequence",
                    description="Explicitly run one ready step using its own Owner approval",
                    input_schema={"type": "object", "properties": {
                        "task_id": {"type": "string", "minLength": 36, "maxLength": 36},
                        "approval_id": {"type": "string", "minLength": 1, "maxLength": 128},
                    }, "required": ["task_id"], "additionalProperties": False}),
        )

    async def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        grant = current_dispatch()
        cap = {"plan_terminal_sequence": (_CREATE, "medium"),
               "advance_terminal_sequence": (_ADVANCE, "high")}.get(name)
        if (cap is None or grant is None or grant.capability_id != cap[0]
                or grant.tool_name != name or grant.risk_level != cap[1]
                or not grant.principal_id or grant.principal_id != self._terminal.principal_id):
            raise CommandSequenceDenied("Exact owner-scoped MCP dispatch required")
        if name == "plan_terminal_sequence":
            if type(arguments) is not dict or set(arguments) != {"commands"}:
                raise ValueError("Only fixed catalog command IDs are accepted")
            commands = arguments["commands"]
            if (type(commands) is not list or not 1 <= len(commands) <= _MAX_STEPS
                    or any(type(x) is not str or x not in self._catalog for x in commands)):
                raise CommandSequenceDenied("Unapproved workflow command")
            return await self._plan(grant.principal_id, commands)
        if (type(arguments) is not dict or set(arguments) - {"task_id", "approval_id"}
                or "task_id" not in arguments
                or type(arguments["task_id"]) is not str
                or not _UUID.fullmatch(arguments["task_id"])):
            raise ValueError("Invalid persisted step identity")
        receipt = arguments.get("approval_id")
        if receipt is not None and (type(receipt) is not str or not 1 <= len(receipt) <= 128):
            raise ValueError("Invalid approval reference")
        return await self._advance(grant.principal_id, arguments["task_id"], receipt)

    async def _plan(self, principal: str, commands: list[str]) -> dict:
        ids = []
        preceding = None
        for command in commands:
            task_id = str(uuid4())
            goal = f"{_MARKER}|{command}|{self._seal(principal, task_id, command, preceding)}"
            try:
                await _await(self._tasks.create_task(
                    principal_id=principal, task_id=task_id, goal=goal,
                    dependencies=(preceding,) if preceding else (),
                ))
            except Exception as exc:
                # Partial created plans remain inert; no command is auto-run.
                raise CommandSequenceUnavailable("Durable sequence creation incomplete") from exc
            ids.append(task_id)
            preceding = task_id
        self._bus.publish(KernelEvent(
            event_type="CommandSequencePlanned", source_component="aura.sequence.coordinator",
            payload={"principal_id": principal, "step_count": len(ids)},
        ))
        return {"task_ids": ids, "state": "created", "trust": "PERSISTED_OWNER_SCOPED_SEQUENCE"}

    async def _advance(self, principal: str, task_id: str, receipt: str | None) -> dict:
        try:
            row = await _await(self._tasks.get(task_id, principal_id=principal))
        except (KeyError, ValueError) as exc:
            raise CommandSequenceDenied("Unknown Owner sequence step") from exc
        segments = row.goal.split("|")
        dependency = row.dependencies[0] if len(row.dependencies) == 1 else None
        if (len(segments) != 3 or segments[0] != _MARKER
                or segments[1] not in self._catalog or len(row.dependencies) > 1
                or not hmac.compare_digest(
                    segments[2], self._seal(principal, task_id, segments[1], dependency),
                )):
            raise CommandSequenceDenied("Unsealed or tampered sequence step")
        command = segments[1]
        if row.state is not TaskState.READY:
            raise CommandSequenceDenied("Step is not READY (no auto-retry or dependency bypass)")
        if receipt is None:
            # Readiness does not imply authorization. Request only: no transition,
            # no Docker dispatch until the separate human approval is consumed.
            try:
                pending = await self._terminal.run(command)
            except (TerminalDenied, TerminalUnavailable) as exc:
                raise CommandSequenceDenied("Terminal policy or approval unavailable") from exc
            if pending.status != "approval_required":
                raise CommandSequenceUnavailable("Terminal authorization was not pending")
            return {"task_id": task_id, "command_id": command,
                    "state": "approval_required", "approval_id": pending.approval_id,
                    "trust": "PERSISTED_OWNER_SCOPED_SEQUENCE"}
        # Enter RUNNING before crossing the high-risk terminal boundary.
        # A crash cannot rerun a possibly executed command; Owner must review.
        try:
            await _await(self._tasks.transition(task_id, principal_id=principal, target=TaskState.RUNNING))
        except (ValueError, KeyError) as exc:
            raise CommandSequenceDenied("Concurrent step or dependency transition denied") from exc
        try:
            result = await self._terminal.run(command, approval_id=receipt)
            if result.status != "executed":
                raise CommandSequenceUnavailable("Terminal was not executed")
            target = TaskState.SUCCEEDED if result.exit_code == 0 else TaskState.FAILED
        except Exception:
            target = TaskState.FAILED
        try:
            completed = await _await(self._tasks.transition(
                task_id, principal_id=principal, target=target,
                result_summary="terminal-exit-0" if target is TaskState.SUCCEEDED else "terminal-failed",
            ))
        except Exception as exc:
            # Leave the task RUNNING; NEVER retry an unknown execution outcome.
            raise CommandSequenceUnavailable("Execution outcome remains unknown") from exc
        self._bus.publish(KernelEvent(
            event_type="CommandSequenceStepFinished", source_component="aura.sequence.coordinator",
            payload={"principal_id": principal, "task_id": task_id, "state": completed.state.value},
        ))
        return {"task_id": task_id, "command_id": command, "state": completed.state.value,
                "approval_id": None, "trust": "PERSISTED_OWNER_SCOPED_SEQUENCE"}


def register_command_sequences(*, services: ServiceRegistry, providers: ProviderRegistry,
                               capabilities: CapabilityRegistry, event_bus: EventBus,
                               tasks: TaskStateMachine | PostgreSQLTaskStateMachine,
                               terminal: GovernedDockerTerminal, hmac_key: bytes,
                               allowed_command_ids: tuple[str, ...]) -> LocalCommandSequenceMCP:
    if not all((isinstance(services, ServiceRegistry), isinstance(providers, ProviderRegistry),
                isinstance(capabilities, CapabilityRegistry), isinstance(event_bus, EventBus))):
        raise TypeError("Existing AURA Core registries required")
    if any(p.definition.provider_id == _PROVIDER for p in providers.records()) or any(capabilities.providers(x) for x in (_CREATE, _ADVANCE)):
        raise ValueError("Sequence provider already registered")
    backend = LocalCommandSequenceMCP(
        tasks=tasks, terminal=terminal, hmac_key=hmac_key, event_bus=event_bus,
        allowed_command_ids=allowed_command_ids,
    )
    service = services.register(ServiceDefinition(
        name="aura-governed-command-sequences", version="1.0.0",
        provider="mcp", category=ServiceCategory.MCP,
    ), object())
    providers.register(ProviderDefinition(
        provider_id=_PROVIDER, name="Durable manual command sequences",
        version="1.0.0", service_id=service.service_id,
    ), backend)
    for cap, tool, risk in (
        (_CREATE, "plan_terminal_sequence", "medium"),
        (_ADVANCE, "advance_terminal_sequence", "high"),
    ):
        capabilities.register(CapabilityDefinition(
            capability_id=cap, name=cap, version="1.0.0",
            description="Manually review and advance persisted isolated command tasks",
            provider_id=_PROVIDER, provider_type=ProviderType.MCP,
            category=CapabilityCategory.AUTOMATION, risk_level=risk, tool_name=tool,
        ))
    return backend


class GovernedCommandSequences:
    def __init__(self, gateway: MCPGateway, *, principal_id: str) -> None:
        if not isinstance(gateway, MCPGateway) or not isinstance(principal_id, str) or not 1 <= len(principal_id) <= 128 or principal_id.strip() != principal_id:
            raise ValueError("Authenticated existing Gateway principal required")
        self._gateway = gateway
        self.principal_id = principal_id

    async def _invoke(self, cap: str, tool: str, args: dict) -> dict:
        try:
            result = await self._gateway.invoke(MCPGatewayRequest(
                request_id="command-sequence:" + str(uuid4()), principal_id=self.principal_id,
                capability_id=cap, operation_id=cap,
                resource_scope=("workflow/commands/plan" if cap == _CREATE else
                                "workflow/commands/advance"),
                risk_level=RiskLevel.MEDIUM if cap == _CREATE else RiskLevel.HIGH,
                tool_name=tool, arguments=args,
            ))
        except Exception as exc:
            raise CommandSequenceUnavailable("Command sequence Gateway unavailable") from exc
        if result.decision is not AuthorizationDecision.ALLOW:
            raise CommandSequenceDenied("Exact sequence policy required")
        raw = result.result
        if result.provider_id != _PROVIDER or not isinstance(raw, dict) or raw.get("trust") != "PERSISTED_OWNER_SCOPED_SEQUENCE":
            raise CommandSequenceUnavailable("Unexpected sequence evidence")
        return raw

    async def plan(self, commands: list[str]) -> SequenceEvidence:
        if type(commands) is not list or not 1 <= len(commands) <= _MAX_STEPS:
            raise ValueError("Bounded command sequence required")
        data = await self._invoke(_CREATE, "plan_terminal_sequence", {"commands": commands})
        ids = data.get("task_ids")
        if (type(ids) is not list or len(ids) != len(commands)
                or any(type(t) is not str or not _UUID.fullmatch(t) for t in ids)
                or data.get("state") != "created"):
            raise CommandSequenceUnavailable("Untrusted plan result")
        return SequenceEvidence(task_ids=tuple(ids), state="created")

    async def advance(self, task_id: str, *, approval_id: str | None = None) -> SequenceEvidence:
        if type(task_id) is not str or not _UUID.fullmatch(task_id):
            raise ValueError("Invalid task identity")
        arguments = {"task_id": task_id}
        if approval_id is not None:
            arguments["approval_id"] = approval_id
        data = await self._invoke(_ADVANCE, "advance_terminal_sequence", arguments)
        if (set(data) != {"task_id", "command_id", "state", "approval_id", "trust"}
                or data["task_id"] != task_id or data["command_id"] is None
                or not _CATALOG.fullmatch(data["command_id"])
                or data["state"] not in {"approval_required", "succeeded", "failed"}
                or (data["state"] == "approval_required") != (type(data["approval_id"]) is str)):
            raise CommandSequenceUnavailable("Malformed step result")
        return SequenceEvidence(task_id=task_id, command_id=data["command_id"],
                                state=data["state"], approval_id=data["approval_id"])


sequence_router = APIRouter(tags=["governed-command-sequences"])


class SequencePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    commands: list[str] = Field(min_length=1, max_length=_MAX_STEPS)


class SequenceAdvanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approval_id: str | None = None


def _reader(request: Request, principal: str) -> GovernedCommandSequences:
    reader = getattr(request.app.state, "governed_command_sequences", None)
    if not isinstance(reader, GovernedCommandSequences):
        raise HTTPException(status_code=503, detail="Command sequences unavailable")
    if reader.principal_id != principal:
        raise HTTPException(status_code=403, detail="Sequence principal mismatch")
    return reader


def _http(result: SequenceEvidence) -> JSONResponse:
    return JSONResponse(
        status_code=202 if result.state == "approval_required" else 200,
        content={"task_ids": list(result.task_ids), "task_id": result.task_id,
                 "command_id": result.command_id, "state": result.state,
                 "approval_id": result.approval_id, "trust": result.trust},
        headers={"Cache-Control": "private, no-store",
                 "X-Content-Type-Options": "nosniff",
                 "Content-Security-Policy": "default-src 'none'; script-src 'none'"},
    )


@sequence_router.post("/api/runtime/command-sequences")
async def http_plan_sequence(body: SequencePlanRequest, request: Request,
                             principal_id: str = Depends(authenticated_principal)) -> JSONResponse:
    try:
        return _http(await _reader(request, principal_id).plan(body.commands))
    except (CommandSequenceDenied, ValueError) as exc:
        raise HTTPException(status_code=403, detail="Sequence plan denied") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Sequence service unavailable") from exc


@sequence_router.post("/api/runtime/command-sequences/{task_id}/advance")
async def http_advance_sequence(task_id: str, body: SequenceAdvanceRequest, request: Request,
                                principal_id: str = Depends(authenticated_principal)) -> JSONResponse:
    try:
        return _http(await _reader(request, principal_id).advance(task_id, approval_id=body.approval_id))
    except (CommandSequenceDenied, ValueError) as exc:
        raise HTTPException(status_code=403, detail="Sequence step denied") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Sequence service unavailable") from exc
