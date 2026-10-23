"""Configuration for the constrained local filesystem MCP provider."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LocalFilesystemMCPConfig:
    provider_id: str = "filesystem.local"
    service_name: str = "aura-local-filesystem"
    service_version: str = "1.0.0"
    capability_id: str = "filesystem.read_test_data"
    operation_id: str = "filesystem.read_test_data"
    tool_name: str = "read_file"
    command: str = sys.executable
    args: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "LocalFilesystemMCPConfig":
        script = Path(__file__).resolve().parents[3] / "scripts" / "aura_local_filesystem_mcp.py"
        raw_args = os.getenv("AURA_FILESYSTEM_MCP_ARGS", "").strip()
        return cls(
            provider_id=os.getenv("AURA_FILESYSTEM_MCP_PROVIDER_ID", "filesystem.local").strip(),
            service_name=os.getenv("AURA_FILESYSTEM_MCP_SERVICE_NAME", "aura-local-filesystem").strip(),
            service_version=os.getenv("AURA_FILESYSTEM_MCP_SERVICE_VERSION", "1.0.0").strip(),
            capability_id=os.getenv("AURA_FILESYSTEM_MCP_CAPABILITY_ID", "filesystem.read_test_data").strip(),
            operation_id=os.getenv("AURA_FILESYSTEM_MCP_OPERATION_ID", "filesystem.read_test_data").strip(),
            tool_name=os.getenv("AURA_FILESYSTEM_MCP_TOOL", "read_file").strip(),
            command=os.getenv("AURA_FILESYSTEM_MCP_COMMAND", sys.executable).strip(),
            args=tuple(raw_args.split("|")) if raw_args else (str(script),),
        )
