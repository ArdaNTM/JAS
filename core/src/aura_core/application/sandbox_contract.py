"""Policy contract for future isolated experiment runners.

This module does not execute code or create containers. Callers must authorize a
job through the Permission Engine/MCP Gateway before selecting a runner.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


RunnerKind = Literal["pyodide", "docker"]


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    """Fail-closed limits shared by browser and backend experiment adapters."""

    max_wall_time_seconds: int = 10
    max_memory_mb: int = 128
    max_input_bytes: int = 64_000
    max_output_bytes: int = 64_000
    network_enabled: bool = False
    host_mounts_enabled: bool = False
    docker_socket_enabled: bool = False
    allow_package_install: bool = False
    allow_persistent_workspace: bool = False

    def __post_init__(self) -> None:
        if not 1 <= self.max_wall_time_seconds <= 300:
            raise ValueError("max_wall_time_seconds must be between 1 and 300")
        if not 16 <= self.max_memory_mb <= 4096:
            raise ValueError("max_memory_mb must be between 16 and 4096")
        if not 1 <= self.max_input_bytes <= 1_000_000:
            raise ValueError("max_input_bytes must be between 1 and 1000000")
        if not 1 <= self.max_output_bytes <= 1_000_000:
            raise ValueError("max_output_bytes must be between 1 and 1000000")
        if self.network_enabled or self.host_mounts_enabled or self.docker_socket_enabled:
            raise ValueError("network, host mounts, and Docker socket must remain disabled")
        if self.allow_package_install or self.allow_persistent_workspace:
            raise ValueError("package installation and persistent workspaces are disabled")


@dataclass(frozen=True, slots=True)
class SandboxJob:
    job_id: str
    principal_id: str
    runner: RunnerKind
    source: str
    input_json: str
    authorization_id: str

    def validate(self, policy: SandboxPolicy) -> None:
        """Validate the request shape only; this method does not authorize or execute."""
        for name, value in (
            ("job_id", self.job_id),
            ("principal_id", self.principal_id),
            ("authorization_id", self.authorization_id),
        ):
            if not value.strip() or len(value) > 200 or any(ord(ch) < 32 for ch in value):
                raise ValueError(f"invalid {name}")
        if len(self.source.encode("utf-8")) > policy.max_input_bytes:
            raise ValueError("source exceeds configured input limit")
        if len(self.input_json.encode("utf-8")) > policy.max_input_bytes:
            raise ValueError("input exceeds configured input limit")
        if self.runner not in ("pyodide", "docker"):
            raise ValueError("unsupported sandbox runner")
