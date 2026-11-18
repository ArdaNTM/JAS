"""Owner-approved local application lifecycle via AURA's existing MCP Gateway.

Trusted composition supplies immutable named executable profiles. Runtime users
cannot select binaries, arguments, environment variables, PIDs or working
directories. High-risk launch/stop REQUIRE CONSUMED Owner approval even when a
caller adds a permissive policy. Only Popen handles created by this provider
may be terminated. This is not a general-purpose terminal or process sandbox.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import stat
import subprocess
from dataclasses import dataclass
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

_PROVIDER = "application.supervisor.local"
_READ = "application.instances.read"
_LAUNCH = "application.launch"
_STOP = "application.stop"
_TOOL_READ = "list_owned_apps"
_TOOL_LAUNCH = "launch_trusted_app"
_TOOL_STOP = "stop_owned_app"
_SCOPES = {
    _READ: "application/owned-instances/read-only",
    _LAUNCH: "application/trusted-catalog/launch",
    _STOP: "application/owned-instances/stop",
}
_ID = re.compile(r"\A[A-Za-z0-9_.:-]{1,64}\Z")
_HEX = re.compile(r"\A[0-9a-f]{64}\Z")
_MAX_EXE_BYTES = 256 * 1024 * 1024
_MAX_PROFILES = 16
_MAX_INSTANCES = 8


class ApplicationDenied(PermissionError):
    """Exact per-operation Gateway authority and consumed approval required."""


class ApplicationUnavailable(RuntimeError):
    """The guarded local lifecycle operation failed without details leakage."""


@dataclass(frozen=True, slots=True)
class TrustedApplication:
    """Configured by trusted code, never from an MCP request or model output."""

    app_id: str
    executable: str
    sha256: str
    argv: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.app_id, str) or not _ID.fullmatch(self.app_id):
            raise ValueError("Invalid trusted application ID")
        if not isinstance(self.executable, str) or not os.path.isabs(self.executable):
            raise ValueError("An absolute trusted executable is mandatory")
        if not isinstance(self.sha256, str) or not _HEX.fullmatch(self.sha256):
            raise ValueError("A lowercase SHA256 executable identity is mandatory")
        if (type(self.argv) is not tuple or len(self.argv) > 12 or
                any(not isinstance(x, str) or len(x) > 1024 or "\x00" in x
                    for x in self.argv)):
            raise ValueError("Invalid immutable application argv")
        if "\x00" in self.executable or len(self.executable) > 2048:
            raise ValueError("Invalid trusted executable path")

    def verify_executable(self) -> str:
        """Verify actual regular executable bytes; never follow path aliases."""
        path = Path(self.executable)
        try:
            if not path.is_file() or path.is_symlink():
                raise ValueError("Trusted executable must be a regular file")
            resolved = path.resolve(strict=True)
            if os.path.normcase(os.path.abspath(self.executable)) != os.path.normcase(str(resolved)):
                raise ValueError("Trusted executable must not traverse symlinks")
            metadata = path.stat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _MAX_EXE_BYTES:
                raise ValueError("Trusted executable identity is unsafe")
            if os.name != "nt" and not os.access(path, os.X_OK):
                raise ValueError("Trusted executable is not executable")
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                while block := stream.read(1024 * 1024):
                    digest.update(block)
            if digest.hexdigest() != self.sha256:
                raise ValueError("Trusted executable digest mismatch")
            return str(resolved)
        except OSError as exc:
            raise ValueError("Trusted executable unavailable") from exc


@dataclass(frozen=True, slots=True)
class AppInstance:
    instance_id: str
    app_id: str
    state: str


@dataclass(frozen=True, slots=True)
class AppLaunchOutcome:
    instance: AppInstance | None
    approval_id: str | None = None

    @property
    def approval_required(self) -> bool:
        return self.approval_id is not None


@dataclass(slots=True)
class _Process:
    principal_id: str
    app_id: str
    handle: subprocess.Popen


class LocalApplicationSupervisorMCP:
    """Real local process launcher with a private per-provider handle table."""

    def __init__(self, profiles: tuple[TrustedApplication, ...], event_bus: EventBus) -> None:
        if not isinstance(event_bus, EventBus):
            raise TypeError("Existing AURA EventBus required")
        self._event_bus = event_bus
        if (not isinstance(profiles, tuple) or not 1 <= len(profiles) <= _MAX_PROFILES
                or any(not isinstance(p, TrustedApplication) for p in profiles)):
            raise ValueError("Trusted immutable composition profiles required")
        ids = [p.app_id for p in profiles]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate application catalog identity")
        self._profiles = {p.app_id: p for p in profiles}
        self._handles: dict[str, _Process] = {}
        self._lock = RLock()

    async def list_tools(self) -> tuple[MCPTool, ...]:
        return (
            MCPTool(name=_TOOL_READ,
                    description="List only applications started by this trusted supervisor",
                    input_schema={"type": "object", "properties": {},
                                  "required": [], "additionalProperties": False}),
            MCPTool(name=_TOOL_LAUNCH,
                    description="Launch a fixed trusted executable after consumed approval",
                    input_schema={"type": "object",
                                  "properties": {"app_id": {"type": "string", "minLength": 1,
                                                            "maxLength": 64}},
                                  "required": ["app_id"], "additionalProperties": False}),
            MCPTool(name=_TOOL_STOP,
                    description="Stop only a private owned process handle after approval",
                    input_schema={"type": "object",
                                  "properties": {"instance_id": {"type": "string",
                                                                  "minLength": 1,
                                                                  "maxLength": 64}},
                                  "required": ["instance_id"], "additionalProperties": False}),
        )

    async def call_tool(self, name: str, arguments: dict | None = None) -> dict[str, object]:
        grant = current_dispatch()
        bindings = {
            _TOOL_READ: (_READ, "low"),
            _TOOL_LAUNCH: (_LAUNCH, "high"),
            _TOOL_STOP: (_STOP, "high"),
        }
        if (grant is None or name not in bindings
                or grant.capability_id != bindings[name][0]
                or grant.risk_level != bindings[name][1]
                or grant.tool_name != name or not grant.principal_id):
            raise ApplicationDenied("Exact authenticated Gateway dispatch required")
        args = arguments if arguments is not None else {}
        if not isinstance(args, dict):
            raise ValueError("Invalid application arguments")
        if name == _TOOL_READ:
            if args:
                raise ValueError("Read-only application query accepts no filters")
            with self._lock:
                instances = [
                    {"instance_id": key, "app_id": entry.app_id,
                     "state": "running" if entry.handle.poll() is None else "exited"}
                    for key, entry in self._handles.items()
                    if entry.principal_id == grant.principal_id
                ]
            return {"instances": instances, "trust": "OWNED_LOCAL_PROCESS_HANDLES"}
        if not grant.approval_consumed:
            raise ApplicationDenied("A separately consumed human approval is mandatory")
        if name == _TOOL_LAUNCH:
            if set(args) != {"app_id"} or type(args["app_id"]) is not str:
                raise ValueError("Invalid trusted application selection")
            return await asyncio.to_thread(self._launch, grant.principal_id, args["app_id"])
        if set(args) != {"instance_id"} or type(args["instance_id"]) is not str:
            raise ValueError("Invalid owned process selection")
        return await asyncio.to_thread(self._stop, grant.principal_id, args["instance_id"])

    def _launch(self, principal_id: str, app_id: str) -> dict[str, object]:
        if app_id not in self._profiles:
            raise ValueError("Unregistered application")
        profile = self._profiles[app_id]
        executable = profile.verify_executable()
        with self._lock:
            for key, entry in list(self._handles.items()):
                if entry.handle.poll() is not None:
                    del self._handles[key]
            if len(self._handles) >= _MAX_INSTANCES:
                raise ApplicationUnavailable("Local application process limit reached")
            # Never inherit arbitrary secrets or shell flags from AURA's runtime.
            env = {name: value for name, value in os.environ.items()
                   if name.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP",
                                        "PATH", "HOME", "USERPROFILE", "LANG"}}
            try:
                handle = subprocess.Popen(
                    (executable, *profile.argv),
                    executable=executable, shell=False, close_fds=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    cwd=str(Path(executable).parent), env=env,
                )
            except (OSError, ValueError) as exc:
                raise ApplicationUnavailable("Trusted application could not start") from exc
            instance_id = str(uuid4())
            self._handles[instance_id] = _Process(
                principal_id=principal_id, app_id=app_id, handle=handle,
            )
        self._event_bus.publish(KernelEvent(
            event_type="ApplicationStarted", source_component="aura.application.supervisor",
            payload={"instance_id": instance_id, "app_id": app_id,
                     "trust": "OWNER_APPROVED_LOCAL_PROCESS"},
        ))
        return {"instance_id": instance_id, "app_id": app_id, "state": "running"}

    def _stop(self, principal_id: str, instance_id: str) -> dict[str, object]:
        if not _ID.fullmatch(instance_id):
            raise ValueError("Invalid owned application instance")
        with self._lock:
            instance = self._handles.get(instance_id)
            if instance is None or instance.principal_id != principal_id:
                raise ApplicationDenied("Instance is not owned by this principal")
            handle = instance.handle
            try:
                if handle.poll() is None:
                    handle.terminate()
                    try:
                        handle.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        handle.kill()
                        handle.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ApplicationUnavailable("Owned application stop failed") from exc
            del self._handles[instance_id]
            self._event_bus.publish(KernelEvent(
                event_type="ApplicationStopped", source_component="aura.application.supervisor",
                payload={"instance_id": instance_id, "app_id": instance.app_id,
                         "trust": "OWNER_APPROVED_LOCAL_PROCESS"},
            ))
            return {"instance_id": instance_id, "app_id": instance.app_id,
                    "state": "stopped"}

    def close(self) -> None:
        """Terminate only subprocess handles created by this provider."""
        with self._lock:
            entries = list(self._handles.items())
        for key, entry in entries:
            try:
                self._stop(entry.principal_id, key)
            except (ApplicationDenied, ApplicationUnavailable, ValueError):
                pass


def register_governed_app_supervisor(
    *, services: ServiceRegistry, providers: ProviderRegistry,
    capabilities: CapabilityRegistry, profiles: tuple[TrustedApplication, ...],
    event_bus: EventBus,
) -> LocalApplicationSupervisorMCP:
    """Explicit trusted composition; no automatic ALLOW policy is installed."""
    if not (isinstance(services, ServiceRegistry)
            and isinstance(providers, ProviderRegistry)
            and isinstance(capabilities, CapabilityRegistry)
            and isinstance(event_bus, EventBus)):
        raise TypeError("Existing Core registries required")
    if any(x.definition.provider_id == _PROVIDER for x in providers.records()):
        raise ValueError("Application supervisor already registered")
    if any(capabilities.providers(k) for k in (_READ, _LAUNCH, _STOP)):
        raise ValueError("Application capabilities are already registered")
    backend = LocalApplicationSupervisorMCP(profiles, event_bus)
    service = services.register(ServiceDefinition(
        name="aura-owned-application-supervisor", version="1.0.0",
        provider="mcp", category=ServiceCategory.MCP,
    ), object())
    providers.register(ProviderDefinition(
        provider_id=_PROVIDER, name="Trusted local application supervisor",
        version="1.0.0", service_id=service.service_id,
    ), backend)
    for cap, tool, risk in (
        (_READ, _TOOL_READ, "low"),
        (_LAUNCH, _TOOL_LAUNCH, "high"),
        (_STOP, _TOOL_STOP, "high"),
    ):
        capabilities.register(CapabilityDefinition(
            capability_id=cap, name="Governed application " + tool,
            version="1.0.0", description="No arbitrary process or shell operations",
            provider_id=_PROVIDER, provider_type=ProviderType.MCP,
            category=CapabilityCategory.AUTOMATION,
            risk_level=risk, tool_name=tool,
        ))
    return backend


class GovernedApplications:
    """Authenticated principal facade; a pending approval NEVER launches."""
    def __init__(self, gateway: MCPGateway, *, authenticated_principal_id: str) -> None:
        if not isinstance(gateway, MCPGateway):
            raise TypeError("Existing MCP Gateway is required")
        if (not isinstance(authenticated_principal_id, str)
                or not 1 <= len(authenticated_principal_id) <= 128
                or authenticated_principal_id.strip() != authenticated_principal_id
                or any(ord(c) < 32 or ord(c) == 127 for c in authenticated_principal_id)):
            raise ValueError("Invalid authenticated application principal")
        self._gateway = gateway
        self._principal = authenticated_principal_id

    async def _call(self, capability: str, tool: str, arguments: dict[str, str],
                    approval_id: str | None = None):
        if approval_id is not None and (not isinstance(approval_id, str)
                                        or not 1 <= len(approval_id) <= 128):
            raise ValueError("Invalid Owner approval receipt")
        try:
            result = await self._gateway.invoke(MCPGatewayRequest(
                request_id="app:" + str(uuid4()), principal_id=self._principal,
                capability_id=capability, operation_id=capability,
                resource_scope=_SCOPES[capability],
                risk_level=RiskLevel.HIGH if capability in (_LAUNCH, _STOP) else RiskLevel.LOW,
                tool_name=tool, arguments=arguments, approval_id=approval_id,
            ))
        except Exception as exc:
            raise ApplicationUnavailable("Local application Gateway unavailable") from exc
        if result.decision is AuthorizationDecision.REQUIRE_APPROVAL:
            if result.approval_id is None:
                raise ApplicationDenied("Explicit human approval required")
            return AppLaunchOutcome(instance=None, approval_id=result.approval_id)
        if result.decision is not AuthorizationDecision.ALLOW:
            raise ApplicationDenied("Application operation not authorized")
        if result.provider_id != _PROVIDER or not isinstance(result.result, dict):
            raise ApplicationUnavailable("Invalid application provider result")
        return result.result

    async def list_owned(self) -> tuple[AppInstance, ...]:
        raw = await self._call(_READ, _TOOL_READ, {})
        if isinstance(raw, AppLaunchOutcome) or raw.get("trust") != "OWNED_LOCAL_PROCESS_HANDLES":
            raise ApplicationUnavailable("Invalid owned application listing")
        data = raw.get("instances")
        if not isinstance(data, list) or len(data) > _MAX_INSTANCES:
            raise ApplicationUnavailable("Invalid owned process count")
        return tuple(self._validate(row, {"running", "exited"}) for row in data)

    @staticmethod
    def _validate(raw: dict, valid_states: set[str]) -> AppInstance:
        if (not isinstance(raw, dict) or set(raw) != {"instance_id", "app_id", "state"}
                or not isinstance(raw["instance_id"], str)
                or not _ID.fullmatch(raw["instance_id"])
                or not isinstance(raw["app_id"], str) or not _ID.fullmatch(raw["app_id"])
                or raw["state"] not in valid_states):
            raise ApplicationUnavailable("Invalid owned application evidence")
        return AppInstance(raw["instance_id"], raw["app_id"], raw["state"])

    async def launch(self, app_id: str, *, approval_id: str | None = None) -> AppLaunchOutcome:
        if not isinstance(app_id, str) or not _ID.fullmatch(app_id):
            raise ValueError("Invalid trusted app ID")
        outcome = await self._call(_LAUNCH, _TOOL_LAUNCH, {"app_id": app_id}, approval_id)
        if isinstance(outcome, AppLaunchOutcome):
            return outcome
        return AppLaunchOutcome(self._validate(outcome, {"running"}))

    async def stop(self, instance_id: str, *, approval_id: str | None = None) -> AppLaunchOutcome:
        if not isinstance(instance_id, str) or not _ID.fullmatch(instance_id):
            raise ValueError("Invalid instance ID")
        outcome = await self._call(_STOP, _TOOL_STOP, {"instance_id": instance_id}, approval_id)
        if isinstance(outcome, AppLaunchOutcome):
            return outcome
        return AppLaunchOutcome(self._validate(outcome, {"stopped"}))
