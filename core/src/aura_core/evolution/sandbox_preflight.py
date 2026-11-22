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
_MAX_TOOLS = 64
_MAX_SCHEMA_JSON_BYTES = 65_536


def _schema_json_size(schemas: dict[str, dict]) -> int:
    """Account for all tool names, schemas, and JSON overhead in UTF-8 bytes."""
    return len(json.dumps(schemas, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True).encode("ascii"))


class SandboxUntrusted(RuntimeError):
    """A candidate cannot be safely started, has failed health, or lacks proof."""


def choose_python_entrypoint(files: dict[str, bytes], hint: str) -> str:
    """Resolve declarative PEP-621 commands ahead of ambiguous filename hints.

    Only bounded TOML and retained Python text are inspected. A selected
    project-script target is not trusted to be an MCP until local multi-module
    AST validation and a real initialize/tools-list handshake have passed.
    """
    import ast
    import tomllib

    projects = sorted(
        (path for path in files if path == "pyproject.toml"
         or path.endswith("/pyproject.toml")),
        key=lambda path: (path.count("/"), path),
    )
    if len(projects) > 16:
        raise SandboxUntrusted("Too many Python project metadata files")
    # Evaluate all safe PEP-621 script targets before choosing. The first
    # command is often a generic CLI (e.g. projectmem.cli), not its stdio MCP
    # server (projectmem.mcp_server). Preserve declaration order on ties.
    script_targets: list[tuple[int, str]] = []
    for config in projects:
        if len(files[config]) > 128_000:
            raise SandboxUntrusted("Oversized pyproject metadata")
        try:
            metadata = tomllib.loads(files[config].decode("utf-8-sig"))
        except (UnicodeError, ValueError) as exc:
            raise SandboxUntrusted("Invalid pyproject TOML") from exc
        project = metadata.get("project", {})
        if not isinstance(project, dict):
            raise SandboxUntrusted("Invalid Python project metadata")
        scripts = project.get("scripts", {})
        if not isinstance(scripts, dict) or len(scripts) > 64:
            raise SandboxUntrusted("Invalid project script mapping")
        prefix = config.removesuffix("pyproject.toml")
        for name, value in scripts.items():
            if not isinstance(name, str) or not isinstance(value, str):
                raise SandboxUntrusted("Invalid project script target")
            target = re.fullmatch(
                r"([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*):([A-Za-z_]\w*)",
                value.strip(),
            )
            if target is None:
                continue
            module = target.group(1).replace(".", "/")
            for rel in (f"src/{module}.py", f"{module}.py",
                        f"src/{module}/__main__.py",
                        f"{module}/__main__.py"):
                path = prefix + rel
                if path in files and path.count("/") <= 10:
                    source = files[path]
                    if len(source) > 512_000:
                        continue
                    markers = any(token in source for token in (
                        b"FastMCP", b"MCPServer", b"mcp.server", b"Server(",
                    ))
                    mcp_named = ("mcp" in name.lower()
                                 or "mcp" in target.group(1).lower())
                    script_targets.append((
                        2 * int(markers) + int(mcp_named), path,
                    ))
                    break
    if script_targets:
        return max(script_targets, key=lambda candidate: candidate[0])[1]

    priority = ("server.py", "main.py", "mcp_server.py", "__main__.py")
    candidates = ([hint] if isinstance(hint, str) and hint in files
                  and hint.endswith(".py") else [])
    candidates.extend(
        path for basename in priority for path in sorted(files)
        if path not in candidates and path.rsplit("/", 1)[-1] == basename
        and (path.startswith("src/") or "/" not in path)
    )
    # Explicit hints win over fallback candidates, but never over valid
    # PEP-621 declarations. A hinted __main__.py may import FastMCP from
    # a sibling. The separate package AST and MCP handshake still gate it.
    if candidates and candidates[0] == hint:
        hinted = files[hint]
        if len(hinted) <= 512_000 and hint.count("/") <= 10:
            try:
                ast.parse(hinted.decode("utf-8-sig"), filename=hint)
            except (UnicodeError, SyntaxError, ValueError):
                pass
            else:
                return hint

    # An entry may only import its FastMCP sibling; allow AST-verifiable
    # module wrappers rather than requiring a FastMCP symbol in *that* file.
    # Runtime execution remains blocked until independent validation.
    deferred = []
    for path in candidates:
        if path not in files or path.count("/") > 10 or len(files[path]) > 512_000:
            continue
        content = files[path]
        if any(s in content for s in
               (b"FastMCP", b"MCPServer", b"mcp.server", b"Server(")):
            return path
        try:
            tree = ast.parse(content.decode("utf-8-sig"), filename=path)
        except (SyntaxError, ValueError, UnicodeError):
            continue
        if any(isinstance(node, (ast.Import, ast.ImportFrom))
               for node in ast.walk(tree)):
            deferred.append(path)
    if deferred:
        return deferred[0]
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

    def _runtime_package_bytes(self, package_name: str) -> int:
        """Measure only an existing runtime package; never follow filesystem links."""
        if (not re.fullmatch(r"[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+", package_name)
                or ".." in package_name):
            raise SandboxUntrusted("Invalid runtime package identity")
        root = self.runtime_root / package_name
        if (root.is_symlink() or (hasattr(root, "is_junction") and root.is_junction())
                or not root.is_dir()):
            raise SandboxUntrusted("Unsafe runtime package directory")
        _checked_path(root)
        total = 0
        for directory, dirs, files in os.walk(root, followlinks=False):
            for name in dirs + files:
                item = Path(directory) / name
                if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
                    raise SandboxUntrusted("Unsafe runtime package link")
                if item.is_file():
                    total += item.stat().st_size
        return total

    def _prune_old_rejected_staging(self) -> None:
        """Remove only aged, demonstrably rejected staging copies.

        Verified sources, runtime, signatures and all Owner receipts are never
        touched. No unknown or active candidate is eligible for deletion.
        """
        staging = self.workspace.root / "staging"
        _checked_path(staging)
        inventory = self.workspace.active
        if (inventory.is_symlink() or not inventory.is_file()
                or inventory.stat().st_size > 200_000):
            raise SandboxUntrusted("Untrusted active capability inventory")
        data = json.loads(inventory.read_text("utf-8"))
        if (not isinstance(data, dict)
                or data.get("schema") != "aura.external-capabilities.v1"
                or not isinstance(data.get("active"), list)
                or len(data["active"]) > self.workspace.max_items):
            raise SandboxUntrusted("Invalid active capability inventory")
        statuses = {}
        for row in data["active"]:
            if isinstance(row, dict) and isinstance(row.get("repository"), str):
                statuses[row["repository"]] = row.get("status")

        rejected: dict[str, int] = {}
        audit = self.workspace.root / "logs" / "staging-rejections.jsonl"
        if audit.exists() or audit.is_symlink():
            if audit.is_symlink() or not audit.is_file() or audit.stat().st_size > 200_000:
                raise SandboxUntrusted("Unsafe staging rejection audit")
            for line in audit.read_text("utf-8").splitlines():
                try:
                    row = json.loads(line)
                except (TypeError, ValueError):
                    continue
                if (isinstance(row, dict) and row.get("status") == "STAGING_REJECTED"
                        and isinstance(row.get("repository"), str)
                        and type(row.get("timestamp")) is int):
                    rejected[row["repository"]] = max(
                        rejected.get(row["repository"], 0), row["timestamp"],
                    )

        cutoff = time.time() - 24 * 3600
        for stage in sorted(staging.iterdir(), key=lambda p: p.lstat().st_mtime):
            if stage.is_symlink() or (hasattr(stage, "is_junction") and stage.is_junction()):
                raise SandboxUntrusted("Unsafe staging directory link")
            if not stage.is_dir() or stage.stat().st_mtime >= cutoff:
                continue
            parts = stage.name.split("__")
            if (len(parts) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part)
                                          and part not in (".", "..") for part in parts)):
                continue
            repository = "/".join(parts)
            status = statuses.get(repository)
            if status not in (None, "QUARANTINED"):
                continue
            # A rejection alone is not evidence against a separately verified
            # package; never prune it on the strength of an old audit record.
            rejected_only = (status is None
                             and not (self.workspace.root / "verified" / stage.name).exists()
                             and rejected.get(repository, 0) >= stage.stat().st_mtime)
            if status != "QUARANTINED" and not rejected_only:
                continue
            _checked_path(stage)
            for directory, dirs, files in os.walk(stage, followlinks=False):
                for child in dirs + files:
                    item = Path(directory) / child
                    if (item.is_symlink() or
                            (hasattr(item, "is_junction") and item.is_junction())):
                        raise SandboxUntrusted("Unsafe staged evidence link")
            shutil.rmtree(stage)

    def _verify_runtime_capacity(
        self, additional_bytes: int, *,
        reattesting_package: str | None = None, baseline_bytes: int = 0,
    ) -> None:
        """Account new allocation without charging an already installed package twice.

        The signed, fingerprint-checked runtime exists before the attestor may
        request revalidation. A fixed baseline credit is shared by before/after
        installation checks; newly installed bytes still consume the quota.
        """
        if (type(additional_bytes) is not int or additional_bytes < 0
                or type(baseline_bytes) is not int or baseline_bytes < 0):
            raise SandboxUntrusted("Invalid evolution storage reservation")
        existing = self.runtime_root / reattesting_package if reattesting_package else None
        if reattesting_package is not None:
            if baseline_bytes <= 0:
                raise SandboxUntrusted("Missing existing runtime baseline")
            self._runtime_package_bytes(reattesting_package)
        elif baseline_bytes:
            raise SandboxUntrusted("Unexpected runtime quota credit")

        total = 0
        existing_total = 0
        folders = 0
        for directory, dirs, files in os.walk(self.runtime_root, followlinks=False):
            current = Path(directory)
            for child in dirs:
                item = current / child
                if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
                    raise SandboxUntrusted("Unsafe runtime directory link")
            if current == self.runtime_root:
                folders = len(dirs)
            for filename in files:
                item = current / filename
                if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
                    raise SandboxUntrusted("Unsafe runtime file link")
                size = item.stat().st_size
                total += size
                if existing is not None and (current == existing or existing in current.parents):
                    existing_total += size
                if total > self.workspace.max_bytes and existing is None:
                    raise SandboxUntrusted("Evolution runtime quota reached")
        if (folders > self.workspace.max_items
                or (folders == self.workspace.max_items and existing is None)):
            raise SandboxUntrusted("Evolution runtime package quota reached")
        credit = min(baseline_bytes, existing_total)
        try:
            usage = self.workspace._usage()
        except StagingRejected as exc:
            if str(exc) != "Evolution storage quota reached":
                raise SandboxUntrusted("Unsafe evolution staging evidence") from exc
            self._prune_old_rejected_staging()
            try:
                usage = self.workspace._usage()
            except StagingRejected as still_full:
                raise SandboxUntrusted("Evolution combined storage quota reached") from still_full
        combined = usage + total - credit + additional_bytes
        if combined >= self.workspace.max_bytes * 9 // 10:
            self._prune_old_rejected_staging()
            try:
                combined = self.workspace._usage() + total - credit + additional_bytes
            except StagingRejected as exc:
                raise SandboxUntrusted("Evolution combined storage quota reached") from exc
        if combined > self.workspace.max_bytes:
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
                    or _schema_json_size({tool.name: tool.input_schema
                                          for tool in tools}) > _MAX_SCHEMA_JSON_BYTES):
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
