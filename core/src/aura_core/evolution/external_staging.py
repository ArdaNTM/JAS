"""Inert, budgeted staging of public GitHub MCP candidates.

Untrusted archives are never imported, built, installed, or executed. Every
remote acquisition is a distinct authorized MCPGateway tool invocation.
Static screening is not a sandbox attestation or a license legal opinion.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import stat
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath

import httpx

from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.evolution.self_discovery import PERMITTED_LICENSES

CAPABILITY = "github.repository.stage"
TOOL = "stage_repository"
SCOPE = "evolution-staging"
_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,80}/[A-Za-z0-9_.-]{1,100}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_FILE = re.compile(r"^[A-Za-z0-9_./-]{1,250}$")
_DENIED_PARTS = frozenset({"", ".", ".."})
_WIN_RESERVED = frozenset({
    "con", "prn", "aux", "nul", *("com" + str(i) for i in range(1, 10)),
    *("lpt" + str(i) for i in range(1, 10)),
})
_PLATFORM = re.compile(
    r"\b(?:mlx|apple.silicon|macos.only|darwin.only|xcode|swiftui)\b",
    re.IGNORECASE,
)
_UNSAFE = re.compile(
    r"\b(?:eval\s*\(|exec\s*\(|os\.system\s*\(|subprocess\."
    r"(?:Popen|run|call)\s*\(|curl\s+[^\r\n]*\|\s*(?:bash|sh)|"
    r"powershell\s+-enc|Invoke-Expression|pickle\.loads\s*\()\b",
    re.IGNORECASE,
)
_PAID = re.compile(
    r"(?i)(?:OPENAI_API_KEY|ANTHROPIC_API_KEY|STRIPE_SECRET_KEY|"
    r"paid\s+(?:subscription|api\s+key)\s+required)",
)
_ENTRY = ("pyproject.toml", "package.json", "server.py", "main.py", "mcp_server.py")
_MAX_ARCHIVE = 3_000_000
_MAX_EXTRACTED = 8_000_000
_MAX_FILE = 750_000
_MAX_FILES = 120


class StagingRejected(ValueError):
    """Untrusted or unsafe candidate cannot be promoted to static review."""


def _checked_path(path: Path) -> Path:
    resolved = path.resolve()
    cursor = path
    for current in (cursor, *cursor.parents):
        if current.is_symlink() or (
            hasattr(current, "is_junction") and current.is_junction()
        ):
            raise StagingRejected("Symlink or junction in evolution storage path")
    return resolved


class EvolutionWorkspace:
    """Outside-checkout isolated storage. Never an execution sandbox."""

    def __init__(self, root: Path | str, *, max_items: int = 24,
                 max_bytes: int = 150_000_000):
        if not 1 <= max_items <= 100 or not 1_000_000 <= max_bytes <= 1_000_000_000:
            raise ValueError("Invalid evolution capacity budget")
        root = Path(root).expanduser()
        if not root.is_absolute():
            raise ValueError("Evolution root must be an absolute path")
        checkout = Path(__file__).resolve().parents[4]
        target = _checked_path(root)
        source = _checked_path(checkout)
        if target == source or target.is_relative_to(source) or source.is_relative_to(target):
            raise PermissionError("Evolution storage must be isolated outside JAS checkout")
        self.root = root
        self.max_items = max_items
        self.max_bytes = max_bytes
        for folder in ("catalog", "staging", "verified", "logs"):
            location = root / folder
            if location.exists() and not location.is_dir():
                raise StagingRejected("Evolution storage path is not a directory")
            location.mkdir(parents=True, exist_ok=True)
            _checked_path(location)
        self.active = root / "active_capabilities.json"
        if self.active.exists() and (self.active.is_symlink() or not self.active.is_file()):
            raise StagingRejected("Invalid active capability inventory")
        if not self.active.exists():
            self.active.write_text(json.dumps({
                "schema": "aura.external-capabilities.v1",
                "active": [],
                "activation_requires": [
                    "verified_independent_sandbox_attestation",
                    "signed_owner_passkey_receipt",
                    "healthy_preregistered_provider",
                    "mcp_gateway_permission_policy",
                ],
            }, indent=2) + "\n", encoding="utf-8")

    def _usage(self) -> int:
        total = 0
        for area in ("staging", "verified"):
            for folder, dirs, files in os.walk(self.root / area, followlinks=False):
                dirs[:] = [name for name in dirs if not (Path(folder) / name).is_symlink()]
                for file in files:
                    p = Path(folder) / file
                    if p.is_symlink():
                        raise StagingRejected("Unexpected link in staged evidence")
                    total += p.stat().st_size
                    if total > self.max_bytes:
                        raise StagingRejected("Evolution storage quota reached")
        return total

    def reserve(self, repository: str, additional_bytes: int):
        if not _NAME.fullmatch(repository):
            raise StagingRejected("Invalid GitHub repository identity")
        key = repository.replace("/", "__")
        stage = self.root / "staging" / key
        verified = self.root / "verified" / key
        _checked_path(stage)
        _checked_path(verified)
        if not verified.exists():
            if len(list((self.root / "verified").iterdir())) >= self.max_items:
                raise StagingRejected("Evolution package count quota reached")
        if self._usage() + additional_bytes > self.max_bytes:
            raise StagingRejected("Evolution storage size quota reached")
        return stage, verified


def _validated_files(archive: bytes) -> tuple[dict[str, bytes], str]:
    if len(archive) > _MAX_ARCHIVE:
        raise StagingRejected("Archive download exceeds maximum byte budget")
    try:
        z = zipfile.ZipFile(io.BytesIO(archive))
    except (zipfile.BadZipFile, OSError) as exc:
        raise StagingRejected("Invalid repository ZIP archive") from exc
    result: dict[str, bytes] = {}
    seen: set[str] = set()
    total = 0
    with z:
        infos = z.infolist()
        if len(infos) > _MAX_FILES + 80:
            raise StagingRejected("Archive has too many members")
        for info in infos:
            raw = info.filename
            if ("\\" in raw or not _FILE.fullmatch(raw)
                    or raw.startswith("/") or raw.startswith(".")):
                raise StagingRejected("Unsafe ZIP entry name")
            segments = PurePosixPath(raw).parts
            if len(segments) < 2 or any(part in _DENIED_PARTS for part in segments):
                raise StagingRejected("Unsafe ZIP path segments")
            relative_parts = segments[1:]
            if any(part.rstrip(" .") != part or
                   part.split(".")[0].lower() in _WIN_RESERVED
                   for part in relative_parts):
                raise StagingRejected("Windows-unsafe archive filename")
            rel = "/".join(relative_parts)
            if len(rel) > 200 or len(relative_parts) > 12:
                raise StagingRejected("Archive nesting budget exceeded")
            mode = (info.external_attr >> 16) & 0o170000
            if mode not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise StagingRejected("ZIP symlink/special file rejected")
            if info.is_dir():
                continue
            key = rel.casefold()
            if key in seen:
                raise StagingRejected("Case-fold duplicate archive member")
            seen.add(key)
            if len(result) >= _MAX_FILES or info.file_size > _MAX_FILE:
                raise StagingRejected("ZIP file budget exceeded")
            if info.file_size > 100 * max(1, info.compress_size):
                raise StagingRejected("ZIP compression ratio exceeded")
            total += info.file_size
            if total > _MAX_EXTRACTED:
                raise StagingRejected("Expanded repository budget exceeded")
            try:
                data = z.read(info)
            except (RuntimeError, OSError, zipfile.BadZipFile) as exc:
                raise StagingRejected("Archive entry cannot be safely read") from exc
            if len(data) != info.file_size:
                raise StagingRejected("Archive member size mismatch")
            if b"\x00" in data[:4096]:
                raise StagingRejected("Binary content is not eligible for static staging")
            result[rel] = data
    if not result:
        raise StagingRejected("No eligible source files found")
    entrypoints = sorted(path for path in result if path.rsplit("/", 1)[-1] in _ENTRY)
    if not entrypoints:
        raise StagingRejected("No recognizable MCP/local Python or JS entrypoint")
    for path, data in result.items():
        if _PLATFORM.search(path):
            raise StagingRejected("Platform-specific macOS/MLX candidate")
        if path.endswith((".py", ".js", ".ts", ".toml", ".json", ".md", ".txt", ".sh")):
            readable = data.decode("utf-8", "replace")
            if _UNSAFE.search(readable) or _PAID.search(readable):
                raise StagingRejected("Static risk/paid API signature detected")
            if path.lower().endswith(("readme.md", "pyproject.toml", "package.json")):
                if _PLATFORM.search(readable):
                    raise StagingRejected("Unsupported macOS-only integration")
    return result, entrypoints[0]


class GitHubStagingMCPProvider:
    """Registered Gateway-only tool: immutable-source snapshot and static audit."""

    def __init__(self, *, workspace: EvolutionWorkspace,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.workspace = workspace
        self._transport = transport

    async def list_tools(self):
        return (MCPTool(
            name=TOOL,
            description="Download bounded GitHub source archive for inert static review",
            input_schema={
                "type": "object",
                "properties": {"repository": {"type": "string", "maxLength": 181}},
                "required": ["repository"],
                "additionalProperties": False,
            },
        ),)

    async def _read(self, client: httpx.AsyncClient, url: str, *,
                    max_bytes: int) -> bytes:
        try:
            async with client.stream("GET", url, headers={
                "User-Agent": "AURA-Evolution-Static-Review/1.0",
                "Accept": "application/vnd.github+json" if "api.github.com" in url
                          else "application/zip",
            }) as response:
                if response.status_code != 200:
                    raise StagingRejected("GitHub archive/metadata unavailable or rate limited")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(data) + len(chunk) > max_bytes:
                        raise StagingRejected("GitHub download byte budget exceeded")
                    data.extend(chunk)
                return bytes(data)
        except httpx.RequestError as exc:
            raise StagingRejected("GitHub archive network request failed") from exc

    async def call_tool(self, name: str, arguments: dict | None = None):
        grant = current_dispatch()
        if (grant is None or grant.principal_id != "local_owner"
                or grant.capability_id != CAPABILITY or grant.tool_name != TOOL):
            raise PermissionError("Only an authorized MCPGateway staging dispatch is accepted")
        if name != TOOL or not isinstance(arguments, dict) or set(arguments) != {"repository"}:
            raise StagingRejected("Unexpected staging tool input")
        repository = arguments["repository"]
        if not isinstance(repository, str) or not _NAME.fullmatch(repository):
            raise StagingRejected("Invalid GitHub repository")
        async with httpx.AsyncClient(
            transport=self._transport, timeout=httpx.Timeout(15.0, connect=5.0),
            follow_redirects=False, trust_env=False,
        ) as client:
            metadata = json.loads(await self._read(
                client, f"https://api.github.com/repos/{repository}", max_bytes=120_000,
            ))
            if (not isinstance(metadata, dict)
                    or metadata.get("full_name") != repository
                    or metadata.get("private") is True
                    or metadata.get("archived") is True
                    or metadata.get("fork") is True
                    or not isinstance(metadata.get("license"), dict)
                    or metadata["license"].get("spdx_id") not in PERMITTED_LICENSES):
                raise StagingRejected("GitHub metadata/license does not satisfy staging policy")
            description = str(metadata.get("description") or "")[:500]
            if _PLATFORM.search(description) or _PAID.search(description):
                raise StagingRejected("Paid or macOS-specific candidate rejected")
            # Pin the snapshot to the current default-branch commit SHA, never
            # interpolate a user-controlled branch/ref into an archive URL.
            commits = json.loads(await self._read(
                client, f"https://api.github.com/repos/{repository}/commits?per_page=1",
                max_bytes=90_000,
            ))
            if not isinstance(commits, list) or not commits:
                raise StagingRejected("No pinned GitHub commit returned")
            sha = commits[0].get("sha") if isinstance(commits[0], dict) else None
            if not isinstance(sha, str) or not _SHA.fullmatch(sha):
                raise StagingRejected("GitHub commit identity is invalid")
            archive = await self._read(
                client, f"https://codeload.github.com/{repository}/zip/{sha}",
                max_bytes=_MAX_ARCHIVE,
            )
        files, entrypoint = _validated_files(archive)
        archive_sha = hashlib.sha256(archive).hexdigest()
        stage, verified = self.workspace.reserve(
            repository, len(archive) * 2 + sum(len(x) for x in files.values()) + 8192
        )
        # No existing evidence is overwritten. The on-disk manifest only
        # points to pinned bytes, not a runnable command or trusted receipt.
        if verified.exists():
            old_manifest = verified / "aura-capability-manifest.json"
            if old_manifest.is_file():
                old = json.loads(old_manifest.read_text("utf-8"))
                if old.get("source_sha256") == archive_sha:
                    return old
            raise StagingRejected("Existing verified package requires independent review")
        if stage.exists():
            raise StagingRejected("Existing staged package requires independent review")
        stage_tmp = Path(tempfile.mkdtemp(prefix=".staging-", dir=self.workspace.root / "staging"))
        verified_tmp = Path(tempfile.mkdtemp(prefix=".verified-", dir=self.workspace.root / "verified"))
        try:
            (stage_tmp / "source.zip").write_bytes(archive)
            for relative, data in files.items():
                target = stage_tmp / "source" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            report = {
                "schema": "aura.static-capability-proposal.v1",
                "repository": repository,
                "url": "https://github.com/" + repository,
                "license_spdx_metadata": metadata["license"]["spdx_id"],
                "git_commit_sha": sha,
                "source_sha256": archive_sha,
                "entrypoint_hint": entrypoint,
                "static_file_count": len(files),
                "static_checks": [
                    "bounded-zip", "no-symlinks", "no-traversal", "no-known-unsafe-pattern",
                    "windows-paths", "license-metadata-allowlist",
                ],
                "status": "READY_FOR_OWNER_REVIEW",
                "sandbox_attested": False,
                "owner_approved": False,
                "activation_performed": False,
                "capability_registered": False,
                "execution_allowed": False,
                "warning": "Static analysis is not a safe-execution proof.",
                "created_at": int(time.time()),
            }
            (verified_tmp / "source.zip").write_bytes(archive)
            (verified_tmp / "aura-capability-manifest.json").write_text(
                json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            stage_tmp.rename(stage)
            verified_tmp.rename(verified)
            return report
        finally:
            if stage_tmp.exists():
                shutil.rmtree(stage_tmp)
            if verified_tmp.exists():
                shutil.rmtree(verified_tmp)
