"""Isolated, untrusted MCP preflight. This does NOT issue signed attestations.

An independent, privileged attestor must evaluate the sandbox run and sign
its own evidence; AURA Core must never sign or substitute a mock receipt.
MCP execution is restricted to digest-pinned Linux Docker images with
network disabled and no host privileges. The Windows desktop is not mounted.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from typing import Any

from mcp.client.stdio import StdioServerParameters

from aura_core.evolution.decision_engine import EvolutionDecisionEngine
from aura_core.evolution.external_staging import (
    EvolutionWorkspace, StagingRejected, _checked_path, _validated_files,
)
from aura_core.mcp.connection import MCPConnection

_IMAGE = re.compile(r"^[a-zA-Z0-9._/-]+@sha256:[0-9a-f]{64}$")
_SERVER = re.compile(r"^[a-zA-Z0-9._/-]{1,150}\.py$")
_MAX_TOOLS = 32


class SandboxUntrusted(RuntimeError):
    """A candidate cannot be safely started, has failed health, or lacks proof."""


def choose_python_entrypoint(files: dict[str, bytes], hint: str) -> str:
    """Prefer an explicit real MCP server over pyproject/package metadata."""
    priority = ("server.py", "main.py", "mcp_server.py")
    if hint in files and hint.endswith(".py"):
        candidates = [hint]
    else:
        candidates = []
    candidates.extend(
        key for basename in priority for key in sorted(files)
        if key.rsplit("/", 1)[-1] == basename and key not in candidates
    )
    for path in candidates:
        if path not in files or path.count("/") > 8:
            continue
        code = files[path]
        if any(signature in code for signature in
               (b"FastMCP", b"mcp.server", b"Server(")):
            return path
    raise SandboxUntrusted("No supported Python MCP entrypoint")


class IsolatedMCPPreflight:
    """Explicit operator-run preflight using an immutable OCI image and stdio.

    Only extracts files already vetted by static staging. No code is imported
    into Core, and result is explicitly UNATTESTED. The persisted evidence
    cannot be used to authorize a provider or MCPGateway invocation.
    """

    def __init__(self, workspace: EvolutionWorkspace, *, image: str,
                 timeout_seconds: int = 20):
        if not _IMAGE.fullmatch(image):
            raise ValueError("Only OCI digest-pinned image references are accepted")
        if type(timeout_seconds) is not int or not 5 <= timeout_seconds <= 60:
            raise ValueError("Sandbox handshake timeout must be 5..60 seconds")
        self.workspace = workspace
        self.image = image
        self.timeout = timeout_seconds
        self.decisions = EvolutionDecisionEngine(workspace)
        self.runtime_root = workspace.root / "runtime"
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        _checked_path(self.runtime_root)

    def _verify_runtime_capacity(self, additional_bytes: int) -> None:
        """Bound runtime footprint against the same external workspace quota."""
        total = 0
        folders = 0
        for directory, dirs, files in os.walk(self.runtime_root, followlinks=False):
            current = Path(directory)
            safe_dirs = []
            for child in dirs:
                item = current / child
                if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
                    raise SandboxUntrusted("Unsafe runtime directory link")
                safe_dirs.append(child)
            dirs[:] = safe_dirs
            if current == self.runtime_root:
                folders = len(dirs)
            for filename in files:
                item = current / filename
                if item.is_symlink():
                    raise SandboxUntrusted("Unsafe runtime file link")
                total += item.stat().st_size
                if total > self.workspace.max_bytes:
                    raise SandboxUntrusted("Evolution runtime quota reached")
        if folders >= self.workspace.max_items:
            raise SandboxUntrusted("Evolution runtime package quota reached")
        if self.workspace._usage() + total + additional_bytes > self.workspace.max_bytes:
            raise SandboxUntrusted("Evolution combined storage quota reached")

    def prepare(self, package_name: str) -> tuple[Path, str, str]:
        """Metadata-only extraction, no third-party installer, no execution."""
        data, repository, digest = self.decisions._check_candidate(package_name)
        source = self.workspace.root / "verified" / package_name / "source.zip"
        with source.open("rb") as archive:
            details: dict[str, object] = {}
            files, _entrypoint, _skipped = _validated_files(archive, summary=details)
        entry = choose_python_entrypoint(files, data.get("entrypoint_hint", ""))

        destination = self.runtime_root / package_name
        if destination.exists():
            _checked_path(destination)
            if destination.is_symlink() or not destination.is_dir():
                raise SandboxUntrusted("Unsafe runtime path")
            raise SandboxUntrusted("Runtime directory already exists; no overwrite")
        # Static staging already bounded the ZIP. Runtime preparation must
        # also count against the *combined* 5 GiB and package-count ceilings.
        self._verify_runtime_capacity(sum(map(len, files.values())) + 4096)
        # Stage in an isolated tempdir under the external runtime root. All
        # relative paths were validated by the hardened ZIP reader.
        with tempfile.TemporaryDirectory(prefix=".preflight-", dir=self.runtime_root) as temporary:
            temp = Path(temporary)
            for relative, content in files.items():
                target = temp.joinpath(*relative.split("/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.resolve().is_relative_to(temp.resolve()):
                    raise SandboxUntrusted("Unsafe extracted source path")
                with target.open("xb") as handle:
                    handle.write(content)
            (temp / ".aura-untrusted-review.json").write_text(json.dumps({
                "repository": repository,
                "source_sha256": digest,
                "status": "PREPARED_UNATTESTED",
                "sandbox_attested": False, "owner_approved": False,
                "execution_allowed": False, "activation_performed": False,
            }, sort_keys=True), encoding="utf-8")
            temp.rename(destination)
        return destination, entry, digest

    def _docker_arguments(self, runtime: Path, entrypoint: str) -> list[str]:
        if runtime.is_symlink() or not runtime.is_dir():
            raise SandboxUntrusted("Runtime directory not isolated")
        # Container filesystem, network and process resources remain constrained.
        return [
            "run", "--rm", "-i", "--network", "none",
            "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", "64", "--memory", "256m", "--cpus", "1.0",
            "--user", "65534:65534", "--tmpfs", "/tmp:rw,nosuid,noexec,size=16m",
            "--mount", f"type=bind,source={runtime},target=/src,readonly",
            "--workdir", "/src", "--entrypoint", "python",
            self.image, "-u", entrypoint,
        ]

    async def probe(self, package_name: str) -> dict[str, Any]:
        """Health probe only. Docker must already be independently provisioned."""
        repository = package_name.replace("__", "/")
        runtime = None
        result = {"repository": repository, "status": "QUARANTINED",
                  "sandbox_attested": False, "activation_performed": False,
                  "tool_count": 0}
        connection = MCPConnection()
        try:
            existing = self.runtime_root / package_name
            if existing.exists():
                from aura_core.evolution.activation_runtime import runtime_fingerprint
                runtime_fingerprint(self.workspace, package_name)
                metadata, _, digest = self.decisions._check_candidate(package_name)
                with (self.workspace.root / "verified" / package_name / "source.zip").open("rb") as source:
                    files, _, _ = _validated_files(source)
                entry = choose_python_entrypoint(files, metadata.get("entrypoint_hint", ""))
                runtime = existing
            else:
                runtime, entry, digest = self.prepare(package_name)
            docker = shutil.which("docker")
            if not docker:
                raise SandboxUntrusted("Docker sandbox runtime unavailable")
            arguments = self._docker_arguments(runtime, entry)
            await asyncio.wait_for(connection.connect_stdio(
                StdioServerParameters(command=docker, args=arguments, env={}),
            ), timeout=self.timeout)
            tools = await asyncio.wait_for(connection.list_tools(), timeout=5)
            if not tools or len(tools) > _MAX_TOOLS:
                raise SandboxUntrusted("MCP tools/list empty or exceeds limit")
            if any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", tool.name)
                   or not isinstance(tool.input_schema, dict) for tool in tools):
                raise SandboxUntrusted("Invalid MCP tool schema")
            if (len({tool.name for tool in tools}) != len(tools)
                    or sum(len(json.dumps(tool.input_schema)) for tool in tools) > 32_000):
                raise SandboxUntrusted("Duplicate tools or oversized MCP schemas")
            result = {
                "repository": repository, "status": "PREPARED_UNATTESTED",
                "source_sha256": digest,
                "detected_tools": [tool.name for tool in tools],
                "tool_schemas": {
                    tool.name: tool.input_schema for tool in tools
                },
                "tool_count": len(tools),
                "sandbox_attested": False,
                "activation_performed": False,
            }
            return result
        except (SandboxUntrusted, StagingRejected, ValueError, OSError,
                TimeoutError, RuntimeError, KeyError) as exc:
            result["reason_code"] = type(exc).__name__
            return result
        finally:
            try:
                await connection.close()
            except (OSError, RuntimeError):
                pass
            self._audit(result)

    def _audit(self, result: dict[str, Any]) -> None:
        path = self.workspace.root / "logs" / "autonomous-preflight.jsonl"
        if path.is_symlink():
            raise SandboxUntrusted("Sandbox audit path cannot be a symlink")
        if path.exists() and path.stat().st_size > 200_000:
            rotated = path.with_suffix(".previous.jsonl")
            if rotated.is_symlink():
                raise SandboxUntrusted("Sandbox audit rotation path is unsafe")
            path.replace(rotated)
        record = {
            "time": int(time.time()),
            "repository": result.get("repository", ""),
            "status": result.get("status", "QUARANTINED"),
            "reason_code": result.get("reason_code", ""),
            "sandbox_attested": False,
            "activation_performed": False,
        }
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Operator-run isolated MCP preflight; NOT an attestor")
    parser.add_argument("--evolution-root", type=Path, required=True)
    parser.add_argument("--package", required=True, help="Validated owner__repository")
    parser.add_argument("--image", required=True, help="Immutable OCI image@sha256:...")
    args = parser.parse_args()
    if os.getenv("AURA_STORAGE_MODE", "local").lower() != "local":
        parser.error("Isolated evolution preflight is local-only")
    workspace = EvolutionWorkspace(args.evolution_root)
    sandbox = IsolatedMCPPreflight(workspace, image=args.image)
    report = asyncio.run(sandbox.probe(args.package))
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "PREPARED_UNATTESTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
