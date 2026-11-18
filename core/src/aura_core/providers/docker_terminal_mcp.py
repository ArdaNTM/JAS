"""Real Docker-engine terminal with immutable commands and one-shot Owner approval.

No host shell, host working-directory mount, arbitrary argv, inherited AURA secret
or network. Execution requires a preloaded digest-pinned image and a sealed set
of Docker hardening flags. Docker daemon privilege is an external deployment gate.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
import re
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from aura_core.security.http_auth import authenticated_principal

from aura_core.kernel.capabilities import CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry

_CAP = "terminal.sandbox.execute"
_PROVIDER = "terminal.docker.offline"
_TOOL = "run_pinned_terminal_command"
_ID = re.compile(r"\A[a-z][a-z0-9_-]{0,47}\Z")
_IMAGE = re.compile(r"\A[a-z0-9][a-z0-9._:/-]{1,180}@sha256:[0-9a-f]{64}\Z")
_MAX_OUTPUT = 8192
_MAX_COMMANDS = 12


class TerminalDenied(PermissionError):
    """Missing exact one-shot human-approved Gateway authority."""


class TerminalUnavailable(RuntimeError):
    """Container engine or isolated command failed; never include raw error."""


@dataclass(frozen=True, slots=True)
class TerminalCommand:
    command_id: str
    image: str
    argv: tuple[str, ...]
    timeout_seconds: int = 10

    def __post_init__(self) -> None:
        if not isinstance(self.command_id, str) or not _ID.fullmatch(self.command_id):
            raise ValueError("Invalid command identity")
        if not isinstance(self.image, str) or not _IMAGE.fullmatch(self.image):
            raise ValueError("An immutable digest-pinned image is required")
        if (type(self.argv) is not tuple or not 1 <= len(self.argv) <= 12
                or any(type(a) is not str or not 1 <= len(a) <= 256
                       or "\x00" in a or any(ord(c) < 32 for c in a) for a in self.argv)):
            raise ValueError("Trusted fixed nonempty command argv required")
        if type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= 20:
            raise ValueError("Bounded terminal timeout required")


def _canonical_pinned_cli(executable: str, sha256: str) -> str:
    if type(executable) is not str or type(sha256) is not str:
        raise ValueError("Trusted Docker CLI identity required")
    p = Path(executable)
    if not p.is_absolute() or p.is_symlink() or p.resolve(strict=True) != p:
        raise ValueError("Canonical non-symlink Docker CLI required")
    info = p.stat()
    if not p.is_file() or not 0 < info.st_size <= 128 * 1024 * 1024:
        raise ValueError("Invalid Docker CLI size")
    if not re.fullmatch("[a-f0-9]{64}", sha256):
        raise ValueError("SHA-256 pin required")
    h = hashlib.sha256()
    with p.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    if h.hexdigest() != sha256 or info.st_size != p.stat().st_size or info.st_mtime_ns != p.stat().st_mtime_ns:
        raise ValueError("Docker CLI digest or identity changed")
    return str(p)


class DockerSandboxEngine:
    """Real local Docker CLI, no pulled images, no host filesystem mounts."""

    def __init__(self, *, docker_executable: str, docker_sha256: str) -> None:
        if os.name != "posix":
            raise TerminalUnavailable("Docker terminal requires separately attested Unix broker")
        self.executable = _canonical_pinned_cli(docker_executable, docker_sha256)

    def run(self, spec: TerminalCommand) -> dict[str, object]:
        if not isinstance(spec, TerminalCommand):
            raise TypeError("Only trusted command profiles may execute")
        name = "aura-terminal-" + uuid4().hex[:20]
        # A fresh tmpfs workspace is *inside* the container. No host bind or
        # Docker socket is mounted into the container and no image is pulled.
        flags = [
            "run", "--rm", "--pull=never", "--name", name,
            "--network=none", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--pids-limit=32",
            "--memory=256m", "--cpus=0.50", "--user=65534:65534",
            "--tmpfs=/workspace:rw,nosuid,noexec,size=16m,mode=1777",
            "--workdir=/workspace",
            "--", spec.image, *spec.argv,
        ]
        # Docker run does not accept a standalone '--' image separator on all
        # versions; the flags above are fixed by code, never user-provided.
        flags.remove("--")
        safe_env = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"}
        process = None
        captured = bytearray()
        try:
            process = subprocess.Popen(
                [self.executable, *flags], shell=False, cwd="/",
                env=safe_env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, close_fds=True,
            )
            assert process.stdout is not None
            def drain() -> None:
                for chunk in iter(lambda: process.stdout.read(4096), b""):
                    if len(captured) < _MAX_OUTPUT:
                        captured.extend(chunk[:_MAX_OUTPUT-len(captured)])
            thread = threading.Thread(target=drain, daemon=True)
            thread.start()
            process.wait(timeout=spec.timeout_seconds)
            thread.join(timeout=2)
            if thread.is_alive():
                raise TerminalUnavailable("Container output drain timed out")
            exit_code = process.returncode
        except (OSError, subprocess.TimeoutExpired, TerminalUnavailable) as exc:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=3)
            raise TerminalUnavailable("Isolated terminal execution unavailable") from exc
        finally:
            # Cleanup by exact generated name; no caller input, no shell.
            # Race-safe best effort even if Docker CLI timed out.
            try:
                subprocess.run(
                    [self.executable, "rm", "-f", name], shell=False, cwd="/",
                    env=safe_env, stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
        return {
            "command_id": spec.command_id,
            "exit_code": exit_code,
            "stdout": captured.decode("utf-8", errors="replace"),
            "trust": "UNTRUSTED_CONTAINER_OUTPUT",
        }


class LocalDockerTerminalMCP:
    def __init__(self, *, engine: DockerSandboxEngine,
                 commands: tuple[TerminalCommand, ...], event_bus: EventBus) -> None:
        if not isinstance(engine, DockerSandboxEngine) or not isinstance(event_bus, EventBus):
            raise TypeError("Real pinned Docker engine and Kernel EventBus required")
        if (type(commands) is not tuple or not 1 <= len(commands) <= _MAX_COMMANDS
                or not all(isinstance(c, TerminalCommand) for c in commands)
                or len({c.command_id for c in commands}) != len(commands)):
            raise ValueError("Explicit unique bounded command catalog required")
        self._engine = engine
        self._commands = {c.command_id: c for c in commands}
        self._bus = event_bus

    async def list_tools(self) -> tuple[MCPTool, ...]:
        return (MCPTool(
            name=_TOOL, description="Run only a preapproved offline Docker command",
            input_schema={"type": "object", "properties": {
                "command_id": {"type": "string", "minLength": 1, "maxLength": 48},
            }, "required": ["command_id"], "additionalProperties": False},
        ),)

    async def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        grant = current_dispatch()
        if (grant is None or grant.capability_id != _CAP
                or grant.tool_name != _TOOL or grant.risk_level != "high"
                or name != _TOOL or not grant.principal_id
                or not grant.approval_consumed):
            raise TerminalDenied("Exact consumed Owner approval required")
        if (type(arguments) is not dict or set(arguments) != {"command_id"}
                or type(arguments["command_id"]) is not str):
            raise TerminalDenied("Only an existing command ID can be provided")
        spec = self._commands.get(arguments["command_id"])
        if spec is None:
            raise TerminalDenied("Unregistered terminal command")
        result = await asyncio.to_thread(self._engine.run, spec)
        self._bus.publish(KernelEvent(
            event_type="GovernedTerminalExecution",
            source_component="aura.terminal.docker",
            payload={"principal_id": grant.principal_id, "command_id": spec.command_id,
                     "exit_code": result["exit_code"], "trust": "UNTRUSTED_CONTAINER_OUTPUT"},
        ))
        return result


def register_docker_terminal(*, services: ServiceRegistry, providers: ProviderRegistry,
                             capabilities: CapabilityRegistry, event_bus: EventBus,
                             engine: DockerSandboxEngine,
                             commands: tuple[TerminalCommand, ...]) -> LocalDockerTerminalMCP:
    if not (isinstance(services, ServiceRegistry) and isinstance(providers, ProviderRegistry)
            and isinstance(capabilities, CapabilityRegistry) and isinstance(event_bus, EventBus)):
        raise TypeError("Existing AURA Core registries required")
    if any(r.definition.provider_id == _PROVIDER for r in providers.records()) or capabilities.providers(_CAP):
        raise ValueError("Terminal provider already registered")
    backend = LocalDockerTerminalMCP(engine=engine, commands=commands, event_bus=event_bus)
    service = services.register(ServiceDefinition(
        name="aura-offline-docker-terminal", version="1.0.0",
        provider="mcp", category=ServiceCategory.MCP,
    ), object())
    providers.register(ProviderDefinition(
        provider_id=_PROVIDER, name="Offline Docker execution sandbox",
        version="1.0.0", service_id=service.service_id,
    ), backend)
    capabilities.register(CapabilityDefinition(
        capability_id=_CAP, name="Approved isolated terminal command",
        version="1.0.0", description="Run preloaded pinned image with fixed argv and no mounts/network",
        provider_id=_PROVIDER, provider_type=ProviderType.MCP,
        category=CapabilityCategory.AUTOMATION, risk_level="high", tool_name=_TOOL,
    ))
    return backend


@dataclass(frozen=True, slots=True)
class TerminalEvidence:
    command_id: str
    status: str
    approval_id: str | None = None
    exit_code: int | None = None
    stdout: str = ""
    trust: str = "UNTRUSTED_CONTAINER_OUTPUT"


class GovernedDockerTerminal:
    def __init__(self, gateway: MCPGateway, *, principal_id: str) -> None:
        if not isinstance(gateway, MCPGateway) or not isinstance(principal_id, str) or not 1 <= len(principal_id) <= 128 or principal_id.strip() != principal_id:
            raise ValueError("Existing MCP Gateway and authenticated principal required")
        self._gateway = gateway
        self.principal_id = principal_id

    async def run(self, command_id: str, *, approval_id: str | None = None) -> TerminalEvidence:
        if not isinstance(command_id, str) or not _ID.fullmatch(command_id):
            raise ValueError("Invalid terminal command ID")
        if approval_id is not None and (not isinstance(approval_id, str) or not 1 <= len(approval_id) <= 128):
            raise ValueError("Invalid terminal approval reference")
        try:
            reply = await self._gateway.invoke(MCPGatewayRequest(
                request_id="terminal:" + str(uuid4()), principal_id=self.principal_id,
                capability_id=_CAP, operation_id=_CAP,
                resource_scope="terminal/sandbox/" + command_id,
                risk_level=RiskLevel.HIGH, tool_name=_TOOL,
                arguments={"command_id": command_id}, approval_id=approval_id,
            ))
        except Exception as exc:
            raise TerminalUnavailable("Isolated terminal Gateway unavailable") from exc
        if reply.decision is AuthorizationDecision.REQUIRE_APPROVAL:
            if approval_id is not None or not reply.approval_id:
                raise TerminalDenied("Approval missing or replayed")
            return TerminalEvidence(command_id=command_id, status="approval_required",
                                    approval_id=reply.approval_id)
        if reply.decision is not AuthorizationDecision.ALLOW:
            raise TerminalDenied("Exact terminal policy required")
        value = reply.result
        if (reply.provider_id != _PROVIDER or not isinstance(value, dict)
                or set(value) != {"command_id", "exit_code", "stdout", "trust"}
                or value["command_id"] != command_id
                or type(value["exit_code"]) is not int
                or not isinstance(value["stdout"], str)
                or len(value["stdout"].encode("utf-8")) > _MAX_OUTPUT * 3
                or value["trust"] != "UNTRUSTED_CONTAINER_OUTPUT"):
            raise TerminalUnavailable("Invalid untrusted container evidence")
        return TerminalEvidence(command_id, "executed", exit_code=value["exit_code"],
                                stdout=value["stdout"])



def load_terminal_config(path: str) -> tuple[DockerSandboxEngine, tuple[TerminalCommand, ...]]:
    """Explicit operator-local configuration, never a model-produced command."""
    if os.name != "posix" or type(path) is not str or not Path(path).is_absolute():
        raise TerminalUnavailable("Only attested Unix operator terminal configuration is supported")
    file = Path(path)
    if file.is_symlink() or file.resolve(strict=True) != file:
        raise TerminalUnavailable("Unsafe terminal configuration path")
    if not file.is_file() or not 0 < file.stat().st_size <= 32768:
        raise TerminalUnavailable("Invalid bounded operator terminal configuration")
    if (file.stat().st_uid != os.getuid() or file.stat().st_mode & 0o077
            or file.parent.stat().st_mode & 0o022):
        raise TerminalUnavailable("Terminal catalog is not private to its owner")
    data = json.loads(file.read_text(encoding="utf-8"))
    if type(data) is not dict or set(data) != {"schema", "docker_executable", "docker_sha256", "commands"} or data["schema"] != "aura.terminal.docker.v1":
        raise ValueError("Unsupported terminal configuration")
    rows = data["commands"]
    if type(rows) is not list or not 1 <= len(rows) <= _MAX_COMMANDS:
        raise ValueError("Invalid command catalog")
    commands = []
    for row in rows:
        if type(row) is not dict or set(row) != {"command_id", "image", "argv", "timeout_seconds"} or type(row["argv"]) is not list:
            raise ValueError("Invalid terminal profile schema")
        commands.append(TerminalCommand(row["command_id"], row["image"],
                                        tuple(row["argv"]), row["timeout_seconds"]))
    if len({c.command_id for c in commands}) != len(commands):
        raise ValueError("Duplicate terminal command ID")
    engine = DockerSandboxEngine(
        docker_executable=data["docker_executable"], docker_sha256=data["docker_sha256"],
    )
    return engine, tuple(commands)


terminal_router = APIRouter(tags=["governed-offline-terminal"])


class TerminalApprovalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approval_id: str | None = None


@terminal_router.post("/api/runtime/terminal/{command_id}")
async def http_run_approved_terminal(
    command_id: str, body: TerminalApprovalBody, request: Request,
    principal_id: str = Depends(authenticated_principal),
) -> JSONResponse:
    reader = getattr(request.app.state, "governed_terminal", None)
    if not isinstance(reader, GovernedDockerTerminal):
        raise HTTPException(status_code=503, detail="Terminal service unavailable")
    if principal_id != reader.principal_id:
        raise HTTPException(status_code=403, detail="Terminal Owner mismatch")
    try:
        result = await reader.run(command_id, approval_id=body.approval_id)
    except (TerminalDenied, ValueError) as exc:
        raise HTTPException(status_code=403, detail="Terminal execution denied") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Terminal backend unavailable") from exc
    return JSONResponse(
        status_code=202 if result.status == "approval_required" else 200,
        content={"command_id": result.command_id, "status": result.status,
                 "approval_id": result.approval_id, "exit_code": result.exit_code,
                 "stdout": result.stdout, "trust": result.trust},
        headers={"Cache-Control": "private, no-store",
                 "X-Content-Type-Options": "nosniff",
                 "Content-Security-Policy": "default-src 'none'; script-src 'none'"},
    )
