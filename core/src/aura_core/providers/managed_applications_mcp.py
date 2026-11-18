"""Opt-in, owner-approved lifecycle for explicitly pinned local applications.

This is NOT a general terminal, process killer, or executable discovery API.
All executable paths/argv are fixed by trusted composition. HIGH-risk start/stop
requires a consumed approval record from the existing MCP Gateway.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass, asdict
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from aura_core.security.http_auth import authenticated_principal
from pathlib import Path
from threading import RLock
from uuid import uuid4

from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType,
)
from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry

_PROVIDER = "applications.managed.local"
_READ = "applications.managed.read"
_START = "applications.managed.start"
_STOP = "applications.managed.stop"
_ID = re.compile(r"\A[a-z][a-z0-9_-]{0,47}\Z")
_DIGEST = re.compile(r"\A[a-f0-9]{64}\Z")
_MAX_APPLICATIONS = 8
_MAX_BINARY_SIZE = 128 * 1024 * 1024


class ManagedAppDenied(PermissionError):
    """The exact authenticated Owner and consumed approval are missing."""


class ManagedAppUnavailable(RuntimeError):
    """Managed local application operation unavailable without leaking details."""


def _hash_executable(path: Path) -> str:
    if path.is_symlink() or path.resolve(strict=True) != path:
        raise ValueError("Executable path must be a canonical non-symlink path")
    if not path.is_file() or not 0 < path.stat().st_size <= _MAX_BINARY_SIZE:
        raise ValueError("Executable missing or outside bounded size")
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError("Executable changed during hashing")
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ManagedApplicationSpec:
    """Only trusted bootstrap/Owner configuration may instantiate this allowlist."""

    app_id: str
    executable: str
    sha256: str
    arguments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.app_id, str) or not _ID.fullmatch(self.app_id):
            raise ValueError("Invalid managed application ID")
        if not isinstance(self.executable, str) or not Path(self.executable).is_absolute():
            raise ValueError("Executable must have an absolute path")
        if not isinstance(self.sha256, str) or not _DIGEST.fullmatch(self.sha256):
            raise ValueError("Exact SHA256 pin required")
        if not isinstance(self.arguments, tuple) or len(self.arguments) > 12:
            raise ValueError("Bounded, fixed argv tuple required")
        for argument in self.arguments:
            if (not isinstance(argument, str) or len(argument) > 512
                    or "\x00" in argument or any(ord(c) < 32 for c in argument)):
                raise ValueError("Invalid fixed application argument")
        if _hash_executable(Path(self.executable)) != self.sha256:
            raise ValueError("Pinned executable integrity mismatch")


def load_managed_app_manifest(path: str) -> tuple[ManagedApplicationSpec, ...]:
    """Load a small operator-maintained manifest; no implicit install/discovery."""
    if not isinstance(path, str) or not Path(path).is_absolute():
        raise ValueError("An absolute trusted manifest path is mandatory")
    p = Path(path)
    if p.is_symlink() or p.resolve(strict=True) != p:
        raise ValueError("Symlink manifest is not trusted")
    if not p.is_file() or p.stat().st_size > 32768:
        raise ValueError("Invalid or oversized application manifest")
    # Fail closed where the source file or its directory can be changed by others.
    if os.name == "nt":
        raise ManagedAppUnavailable(
            "Windows manifest requires independent Owner NTFS ACL attestation"
        )
    for part in (p, p.parent):
        if part.stat().st_mode & 0o022:
            raise ValueError("Manifest trust path is group/world writable")
    if p.stat().st_uid != os.getuid():
        raise ValueError("Manifest must be owned by the effective local operator")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"schema", "applications"} or (
            data["schema"] != "aura.managed-apps.v1"):
        raise ValueError("Unknown application manifest schema")
    rows = data["applications"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= _MAX_APPLICATIONS:
        raise ValueError("Invalid managed application count")
    specs = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"app_id", "executable", "sha256", "arguments"}:
            raise ValueError("Unknown application manifest field")
        if not isinstance(row["arguments"], list):
            raise ValueError("Arguments must be an array")
        specs.append(ManagedApplicationSpec(
            row["app_id"], row["executable"], row["sha256"], tuple(row["arguments"]),
        ))
    if len({spec.app_id for spec in specs}) != len(specs):
        raise ValueError("Duplicate application ID")
    return tuple(specs)


class LocalManagedApplicationsMCP:
    def __init__(self, specifications: tuple[ManagedApplicationSpec, ...],
                 *, event_bus: EventBus | None = None) -> None:
        if (not isinstance(specifications, tuple) or not 1 <= len(specifications) <= _MAX_APPLICATIONS
                or not all(isinstance(s, ManagedApplicationSpec) for s in specifications)
                or len({s.app_id for s in specifications}) != len(specifications)):
            raise ValueError("Explicit bounded application allowlist required")
        self._specs = {s.app_id: s for s in specifications}
        self._owned: dict[tuple[str, str], subprocess.Popen] = {}
        self._lock = RLock()
        self._event_bus = event_bus

    async def list_tools(self) -> tuple[MCPTool, ...]:
        app_input = {
            "type": "object",
            "properties": {"app_id": {"type": "string", "minLength": 1, "maxLength": 48}},
            "required": ["app_id"], "additionalProperties": False,
        }
        return (
            MCPTool(name="list_managed_applications",
                    description="Read only explicitly managed process status",
                    input_schema={"type": "object", "properties": {}, "required": [],
                                  "additionalProperties": False}),
            MCPTool(name="start_managed_application",
                    description="Start an approved, digest-pinned executable",
                    input_schema=app_input),
            MCPTool(name="stop_managed_application",
                    description="Stop only a child launched by this provider",
                    input_schema=app_input),
        )

    def _publish(self, app_id: str, principal: str, state: str) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(KernelEvent(
                event_type="ManagedApplicationStateChanged",
                source_component="aura.managed_applications",
                payload={"app_id": app_id, "principal_id": principal, "state": state},
            ))

    def _start(self, principal: str, app_id: str) -> dict:
        spec = self._specs[app_id]
        with self._lock:
            key = (principal, app_id)
            previous = self._owned.get(key)
            if previous is not None and previous.poll() is None:
                return {"app_id": app_id, "state": "running", "principal_id": principal}
            if _hash_executable(Path(spec.executable)) != spec.sha256:
                raise ManagedAppUnavailable("Pinned application integrity changed")
            # Fixed trusted argv; never invoke shell or accept caller-supplied command.
            child = subprocess.Popen(
                [spec.executable, *spec.arguments],
                shell=False, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                cwd=str(Path(spec.executable).parent), close_fds=True,
            )
            self._owned[key] = child
        self._publish(app_id, principal, "running")
        return {"app_id": app_id, "state": "running", "principal_id": principal}

    @staticmethod
    def _terminate(child: subprocess.Popen) -> None:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=2)

    def _stop(self, principal: str, app_id: str) -> dict:
        with self._lock:
            key = (principal, app_id)
            child = self._owned.get(key)
            if child is None:
                raise ManagedAppUnavailable("Application is not owned by this session")
            self._terminate(child)
            self._owned.pop(key, None)
        self._publish(app_id, principal, "stopped")
        return {"app_id": app_id, "state": "stopped", "principal_id": principal}

    def _read(self, principal: str) -> dict:
        with self._lock:
            rows = [
                {"app_id": app_id, "state": ("running" if child.poll() is None else "stopped")}
                for (owner, app_id), child in sorted(self._owned.items())
                if owner == principal
            ]
        return {"apps": rows, "principal_id": principal, "trust": "LOCAL_MANAGED_CHILD"}

    async def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        grant = current_dispatch()
        mapping = {
            "list_managed_applications": (_READ, "low"),
            "start_managed_application": (_START, "high"),
            "stop_managed_application": (_STOP, "high"),
        }
        if (name not in mapping or grant is None
                or grant.capability_id != mapping[name][0]
                or grant.risk_level != mapping[name][1]
                or grant.tool_name != name or not grant.principal_id):
            raise ManagedAppDenied("MCP Gateway dispatch is required")
        if name == "list_managed_applications":
            if arguments not in ({}, None):
                raise ValueError("Read accepts no arguments")
            return self._read(grant.principal_id)
        if not grant.approval_consumed:
            raise ManagedAppDenied("A consumed Owner approval is required")
        if (not isinstance(arguments, dict) or set(arguments) != {"app_id"}
                or type(arguments["app_id"]) is not str
                or arguments["app_id"] not in self._specs):
            raise ManagedAppDenied("Unknown managed application")
        app_id = arguments["app_id"]
        if name == "start_managed_application":
            return await asyncio.to_thread(self._start, grant.principal_id, app_id)
        return await asyncio.to_thread(self._stop, grant.principal_id, app_id)

    def close(self) -> None:
        with self._lock:
            children = tuple(self._owned.values())
            self._owned.clear()
        for child in children:
            try:
                self._terminate(child)
            except (OSError, subprocess.TimeoutExpired):
                pass


def register_managed_applications(*, services: ServiceRegistry,
                                  providers: ProviderRegistry,
                                  capabilities: CapabilityRegistry,
                                  specifications: tuple[ManagedApplicationSpec, ...],
                                  event_bus: EventBus | None = None) -> LocalManagedApplicationsMCP:
    if not (isinstance(services, ServiceRegistry)
            and isinstance(providers, ProviderRegistry)
            and isinstance(capabilities, CapabilityRegistry)):
        raise TypeError("Authoritative Core registries required")
    if any(r.definition.provider_id == _PROVIDER for r in providers.records()):
        raise ValueError("Managed application provider already registered")
    for cap in (_READ, _START, _STOP):
        if capabilities.providers(cap):
            raise ValueError("Managed application capability already registered")
    backend = LocalManagedApplicationsMCP(specifications, event_bus=event_bus)
    try:
        service = services.register(ServiceDefinition(
            name="aura-managed-applications", version="1.0.0",
            provider="mcp", category=ServiceCategory.MCP,
        ), object())
        providers.register(ProviderDefinition(
            provider_id=_PROVIDER, name="Owner approved local applications",
            version="1.0.0", service_id=service.service_id,
        ), backend)
        for cap, tool, risk in (
            (_READ, "list_managed_applications", "low"),
            (_START, "start_managed_application", "high"),
            (_STOP, "stop_managed_application", "high"),
        ):
            capabilities.register(CapabilityDefinition(
                capability_id=cap, name=cap, version="1.0.0",
                description="Bounded local child process lifecycle",
                provider_id=_PROVIDER, provider_type=ProviderType.MCP,
                category=CapabilityCategory.AUTOMATION, risk_level=risk,
                tool_name=tool,
            ))
    except Exception:
        backend.close()
        raise
    return backend


@dataclass(frozen=True, slots=True)
class ManagedAppOutcome:
    app_id: str
    state: str
    approval_id: str | None = None


class GovernedManagedApplications:
    """Approval is decided independently via AURA's authenticated approval store."""

    def __init__(self, gateway: MCPGateway, *, authenticated_principal_id: str) -> None:
        if not isinstance(gateway, MCPGateway):
            raise TypeError("Existing MCP Gateway required")
        if (not isinstance(authenticated_principal_id, str) or not 1 <= len(authenticated_principal_id) <= 128
                or authenticated_principal_id.strip() != authenticated_principal_id
                or any(ord(c) < 32 or ord(c) == 127 for c in authenticated_principal_id)):
            raise ValueError("Invalid authenticated principal")
        self._gateway = gateway
        self.principal_id = authenticated_principal_id

    async def _invoke(self, capability: str, tool: str, app_id: str | None = None,
                      approval_id: str | None = None) -> ManagedAppOutcome | tuple[ManagedAppOutcome, ...]:
        if app_id is not None and (not isinstance(app_id, str) or not _ID.fullmatch(app_id)):
            raise ValueError("Invalid app_id")
        if approval_id is not None and (not isinstance(approval_id, str) or not 1 <= len(approval_id) <= 128):
            raise ValueError("Invalid approval ID")
        scope = ("applications/managed/read-only" if app_id is None else
                 f"applications/managed/{app_id}/lifecycle")
        try:
            response = await self._gateway.invoke(MCPGatewayRequest(
                request_id="managed-app:" + str(uuid4()),
                principal_id=self.principal_id, capability_id=capability,
                operation_id=capability, resource_scope=scope,
                risk_level=RiskLevel.LOW if app_id is None else RiskLevel.HIGH,
                tool_name=tool, arguments={} if app_id is None else {"app_id": app_id},
                approval_id=approval_id,
            ))
        except Exception as exc:
            raise ManagedAppUnavailable("Managed application Gateway unavailable") from exc
        if response.decision is AuthorizationDecision.REQUIRE_APPROVAL:
            if app_id is None or approval_id is not None or not response.approval_id:
                raise ManagedAppDenied("Approval workflow unavailable or not consumed")
            return ManagedAppOutcome(app_id, "approval_required", response.approval_id)
        if response.decision is not AuthorizationDecision.ALLOW:
            raise ManagedAppDenied("Exact managed application permission required")
        value = response.result
        if response.provider_id != _PROVIDER or not isinstance(value, dict):
            raise ManagedAppUnavailable("Unexpected managed application response")
        if app_id is None:
            if (set(value) != {"apps", "principal_id", "trust"}
                    or value["principal_id"] != self.principal_id
                    or value["trust"] != "LOCAL_MANAGED_CHILD"
                    or not isinstance(value["apps"], list)
                    or len(value["apps"]) > _MAX_APPLICATIONS):
                raise ManagedAppUnavailable("Malformed application inventory")
            rows = []
            for row in value["apps"]:
                if (not isinstance(row, dict) or set(row) != {"app_id", "state"}
                        or not isinstance(row["app_id"], str) or not _ID.fullmatch(row["app_id"])
                        or row["state"] not in ("running", "stopped")):
                    raise ManagedAppUnavailable("Malformed managed application state")
                rows.append(ManagedAppOutcome(row["app_id"], row["state"]))
            return tuple(rows)
        if (set(value) != {"app_id", "state", "principal_id"}
                or value["app_id"] != app_id or value["principal_id"] != self.principal_id
                or value["state"] not in ("running", "stopped")):
            raise ManagedAppUnavailable("Untrusted application operation result")
        return ManagedAppOutcome(app_id, value["state"])

    async def read(self) -> tuple[ManagedAppOutcome, ...]:
        return await self._invoke(_READ, "list_managed_applications")

    async def start(self, app_id: str, *, approval_id: str | None = None) -> ManagedAppOutcome:
        return await self._invoke(_START, "start_managed_application", app_id, approval_id)

    async def stop(self, app_id: str, *, approval_id: str | None = None) -> ManagedAppOutcome:
        return await self._invoke(_STOP, "stop_managed_application", app_id, approval_id)


managed_applications_router = APIRouter(tags=["governed-managed-applications"])


class ApprovalReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approval_id: str | None = None


def _http_reader(request: Request, principal_id: str) -> GovernedManagedApplications:
    service = getattr(request.app.state, "managed_applications", None)
    if not isinstance(service, GovernedManagedApplications):
        raise HTTPException(status_code=503, detail="Managed applications disabled")
    if principal_id != service.principal_id:
        raise HTTPException(status_code=403, detail="Managed app principal mismatch")
    return service


def _http_response(outcome: ManagedAppOutcome | tuple[ManagedAppOutcome, ...]) -> JSONResponse:
    if isinstance(outcome, tuple):
        payload = {"applications": [asdict(x) for x in outcome], "read_only": True}
        status = 200
    else:
        payload = asdict(outcome)
        status = 202 if outcome.state == "approval_required" else 200
    return JSONResponse(
        status_code=status, content=payload,
        headers={"Cache-Control": "private, no-store",
                 "Content-Security-Policy": "default-src 'none'; script-src 'none'",
                 "X-Content-Type-Options": "nosniff"},
    )


@managed_applications_router.get("/api/runtime/managed-apps")
async def http_managed_applications(
    request: Request, principal_id: str = Depends(authenticated_principal),
) -> JSONResponse:
    reader = _http_reader(request, principal_id)
    try:
        return _http_response(await reader.read())
    except ManagedAppDenied as exc:
        raise HTTPException(status_code=403, detail="Managed app read denied") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Managed app service unavailable") from exc


@managed_applications_router.post("/api/runtime/managed-apps/{app_id}/start")
async def http_start_managed_application(
    app_id: str, body: ApprovalReference, request: Request,
    principal_id: str = Depends(authenticated_principal),
) -> JSONResponse:
    reader = _http_reader(request, principal_id)
    try:
        return _http_response(await reader.start(app_id, approval_id=body.approval_id))
    except (ManagedAppDenied, ValueError) as exc:
        raise HTTPException(status_code=403, detail="Managed start denied") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Managed start unavailable") from exc


@managed_applications_router.post("/api/runtime/managed-apps/{app_id}/stop")
async def http_stop_managed_application(
    app_id: str, body: ApprovalReference, request: Request,
    principal_id: str = Depends(authenticated_principal),
) -> JSONResponse:
    reader = _http_reader(request, principal_id)
    try:
        return _http_response(await reader.stop(app_id, approval_id=body.approval_id))
    except (ManagedAppDenied, ValueError) as exc:
        raise HTTPException(status_code=403, detail="Managed stop denied") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Managed stop unavailable") from exc
