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
from urllib.parse import urljoin, urlsplit
from pathlib import Path, PurePosixPath

import httpx

from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.evolution.self_discovery import (
    PERMITTED_LICENSES, GITHUB_RESPONSE_MAX_BYTES, _github_token,
)

CAPABILITY = "github.repository.stage"
TOOL = "stage_repository"
SCOPE = "evolution-staging"  # legacy label, not an authorization resource


def staging_scope(workspace: "EvolutionWorkspace") -> str:
    """Authorize only the exact external staging destination for this operation."""
    return str((workspace.root / "staging").resolve())


def local_staging_policy(workspace: "EvolutionWorkspace"):
    from aura_core.kernel.permissions import (
        AuthorizationDecision, AuthorizationLevel, PermissionPolicy,
    )
    return PermissionPolicy(
        policy_id="local-owner:evolution-static-staging:external-only",
        policy_version="1.0.0", principal_id="local_owner",
        capability_id=CAPABILITY, operation_id=CAPABILITY,
        resource_scope=staging_scope(workspace),
        authorization_level=AuthorizationLevel.WRITE,
        decision=AuthorizationDecision.ALLOW,
    )
_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,80}/[A-Za-z0-9_.-]{1,100}$")


def _valid_repository(value: object) -> bool:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        return False
    return all(part not in (".", "..") and not part.endswith(".")
               for part in value.split("/"))
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
    # Broad process/network imports are normal for MCP servers. Reject only
    # high-confidence obfuscated execution, reverse shells, and direct static-IP
    # credential exfiltration. Inert static screening is NOT sandbox attestation.
    r"(?i)(?:\b(?:eval|exec)\s*\(\s*(?:base64\.)?b64decode\s*\("
    r"|\b(?:eval|exec)\s*\(\s*base64\.b64decode\s*\("
    r"|\b(?:eval|exec)\s*\(\s*atob\s*\("
    r"|\b(?:bash|sh)\s+-i\s*>?\s*&\s*/dev/tcp/"
    r"|\bnc\s+-e\s+/bin/(?:sh|bash)\b"
    r"|\bcurl\s+[^\r\n]*\|\s*(?:bash|sh)\b"
    r"|\b(?:requests|httpx)\.post\s*\(\s*['\"]https?://"
    r"(?:\d{1,3}\.){3}\d{1,3}[^'\"]*['\"][\s\S]{0,400}"
    r"(?:os\.getenv|os\.environ|token|secret|password))",
)
_PAID = re.compile(
    r"(?i)(?:OPENAI_API_KEY|ANTHROPIC_API_KEY|STRIPE_SECRET_KEY|"
    r"BRIGHTDATA_API_KEY|SHODAN_API_KEY|VIRUSTOTAL_API_KEY|"
    r"BASECAMP_ACCESS_TOKEN|paid\s+(?:subscription|api\s+key)\s+required)",
)
_ENTRY = (
    "pyproject.toml", "package.json", "server.py", "main.py", "__main__.py",
    "mcp_server.py", "index.ts", "index.js", "index.mjs", "index.cjs",
)
_MIB = 1024 * 1024
_GIB = 1024 * _MIB
_MAX_ARCHIVE = 256 * _MIB
_MAX_EXTRACTED = 512 * _MIB
_MAX_FILE = 32 * _MIB
_MAX_ARCHIVE_MEMBERS = 25_000
_MAX_STATIC_FILES = 25_000
_MAX_STATIC_BYTES = 64 * _MIB
_SKIP_DIRS = frozenset({
    "docs", "doc", "images", "img", "assets", "media", "videos",
    "examples", "benchmarks", "fixtures", "testdata", ".github",
    "node_modules", "vendor", "tests", "test",
})
_SOURCE_SUFFIXES = frozenset({".py", ".ts", ".js", ".mjs", ".cjs"})
_PASSIVE_SUFFIXES = frozenset({
    ".svg", ".pdf", ".sqlite", ".db", ".lock", ".jsonl", ".csv",
    ".parquet", ".arrow", ".zip", ".gz", ".tar", ".7z", ".rar",
    ".dat",
})
# Only non-executable, well-known binary assets may be omitted from static
# inspection. Unknown binary payloads and executable formats always reject.
_PASSIVE_ASSET_SUFFIXES = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".avif",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp3", ".wav", ".ogg",
    ".mp4", ".webm",
})
# These files can be active when executed directly, but staging never does so.
# Keep only Python/JS source; record textual helpers as skipped_non_source.
_SKIP_SCRIPT_SUFFIXES = frozenset({".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd"})
_EXECUTABLE_SUFFIXES = frozenset({
    ".exe", ".dll", ".so", ".dylib", ".pyd", ".node", ".jar", ".class",
    ".wasm", ".msi", ".com", ".scr", ".vbs",
    ".pyc", ".pyo", ".app", ".deb", ".rpm", ".apk", ".bin",
    ".sys",
})


def _budget(name: str, default: int, minimum: int, maximum: int) -> int:
    label = {
        "AURA_EVOLUTION_MAX_DOWNLOAD_BYTES": "download",
        "AURA_EVOLUTION_MAX_EXTRACTED_BYTES": "extracted",
        "AURA_EVOLUTION_MAX_FILE_BYTES": "file",
        "AURA_EVOLUTION_MAX_ARCHIVE_MEMBERS": "member",
        "AURA_EVOLUTION_MAX_BYTES": "workspace",
        "AURA_EVOLUTION_MAX_ITEMS": "item",
    }.get(name, "capacity")
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise StagingRejected("Invalid evolution " + label + " budget") from exc
    if not minimum <= value <= maximum:
        raise StagingRejected("Invalid evolution " + label + " budget")
    return value


def _archive_budget() -> int:
    return _budget("AURA_EVOLUTION_MAX_DOWNLOAD_BYTES", _MAX_ARCHIVE,
                   _MIB, 512 * _MIB)


def _extracted_budget() -> int:
    return _budget("AURA_EVOLUTION_MAX_EXTRACTED_BYTES", _MAX_EXTRACTED,
                   _MIB, 1024 * _MIB)


def _file_budget() -> int:
    return _budget("AURA_EVOLUTION_MAX_FILE_BYTES", _MAX_FILE,
                   1024, 64 * _MIB)


def _archive_member_budget() -> int:
    """Bound all ZIP entries, including directories and skipped binary assets."""
    return _budget("AURA_EVOLUTION_MAX_ARCHIVE_MEMBERS", _MAX_ARCHIVE_MEMBERS,
                   1, 50_000)


class StagingRejected(ValueError):
    """Untrusted or unsafe candidate cannot be promoted to static review."""


class WorkspacePruneError(StagingRejected):
    """Bounded diagnostic; never expose filesystem paths or arbitrary text."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _prune_path(path: Path, code: str) -> None:
    try:
        _checked_path(path)
    except (OSError, ValueError, RuntimeError) as exc:
        raise WorkspacePruneError(code, "Unsafe or inaccessible cleanup path") from exc


def _raise_walk_error(error: OSError) -> None:
    raise error


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

    def __init__(self, root: Path | str, *, max_items: int | None = None,
                 max_bytes: int | None = None):
        if max_items is None:
            max_items = _budget("AURA_EVOLUTION_MAX_ITEMS", 100, 1, 250)
        if max_bytes is None:
            max_bytes = _budget("AURA_EVOLUTION_MAX_BYTES", 8 * _GIB,
                                1_000_000, 10 * _GIB)
        if not 1 <= max_items <= 250 or not 1_000_000 <= max_bytes <= 10 * _GIB:
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

    def audit(self, *, action: str, repository: str, result: str) -> None:
        # Bounded metadata-only audit. Never persist archive contents,
        # environment variables, credentials or arbitrary error strings.
        if (not re.fullmatch(r"[a-z_]{3,32}", action)
                or not _valid_repository(repository)
                or not re.fullmatch(r"[A-Z_]{3,40}", result)):
            raise ValueError("Invalid evolution audit record")
        destination = self.root / "logs" / "discovery.jsonl"
        if destination.is_symlink():
            raise StagingRejected("Audit log cannot be a symlink")
        if destination.exists() and destination.stat().st_size > 200_000:
            rotated = destination.with_suffix(".previous.jsonl")
            if rotated.is_symlink():
                raise StagingRejected("Audit rotation target cannot be a symlink")
            destination.replace(rotated)
        with destination.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({
                "timestamp": int(time.time()),
                "action": action, "repository": repository, "result": result,
            }, sort_keys=True) + "\n")

    def verified_packages(self, limit: int = 20) -> list[dict[str, object]]:
        # Read-only summaries. Never interpret a manifest as authorization.
        summary = []
        directory = self.root / "verified"
        for package in sorted(directory.iterdir()):
            if len(summary) >= max(1, min(50, limit)):
                break
            if package.is_symlink() or not package.is_dir():
                continue
            manifest = package / "aura-capability-manifest.json"
            if manifest.is_symlink() or not manifest.is_file():
                continue
            try:
                if manifest.stat().st_size > 16000:
                    continue
                data = json.loads(manifest.read_text("utf-8"))
                if (data.get("status") != "READY_FOR_OWNER_REVIEW"
                        or not _valid_repository(data.get("repository", ""))
                        or data.get("repository", "").replace("/", "__") != package.name
                        or data.get("sandbox_attested") is not False
                        or data.get("activation_performed") is not False):
                    continue
                summary.append({
                    "repository": data["repository"],
                    "source_sha256": data.get("source_sha256"),
                    "license": data.get("license_spdx_metadata"),
                    "entrypoint_hint": data.get("entrypoint_hint"),
                    "status": "READY_FOR_OWNER_REVIEW",
                    "sandbox_attested": False,
                    "activation_performed": False,
                })
            except (OSError, ValueError, TypeError, AttributeError):
                continue
        return summary

    def audit_rejection(self, repository: str, reason: str) -> None:
        if not _valid_repository(repository):
            raise ValueError("Invalid audit repository")
        # Bounded, printable metadata only; do not log arbitrary request data.
        safe_reason = "".join(c for c in reason if c.isprintable())[:160]
        destination = self.root / "logs" / "staging-rejections.jsonl"
        if destination.is_symlink():
            raise StagingRejected("Audit log cannot be a symlink")
        if destination.exists() and destination.stat().st_size > 200_000:
            rotated = destination.with_suffix(".previous.jsonl")
            if rotated.is_symlink():
                raise StagingRejected("Audit rotation target cannot be a symlink")
            destination.replace(rotated)
        with destination.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({
                "timestamp": int(time.time()), "repository": repository,
                "reason": safe_reason, "status": "STAGING_REJECTED",
            }, sort_keys=True) + "\n")

    def prune_rejected_staging(self, *, max_directories: int = 12) -> int:
        """Prune only aged quarantined or audit-rejected inert staging copies.

        No runtime, verified source, Owner approval or independent evidence is
        modified. Unsafe links, forged inventory or uncertain status fail closed.
        """
        if type(max_directories) is not int or not 1 <= max_directories <= 12:
            raise StagingRejected("Invalid staging prune budget")
        staging = self.root / "staging"
        _checked_path(staging)
        if (self.active.is_symlink() or not self.active.is_file()
                or self.active.stat().st_size > 200_000):
            raise StagingRejected("Untrusted active capability inventory")
        inventory = json.loads(self.active.read_text("utf-8"))
        if (not isinstance(inventory, dict)
                or inventory.get("schema") != "aura.external-capabilities.v1"
                or not isinstance(inventory.get("active"), list)
                or len(inventory["active"]) > self.max_items):
            raise StagingRejected("Invalid active capability inventory")
        statuses: dict[str, str] = {}
        for row in inventory["active"]:
            if not isinstance(row, dict) or not _valid_repository(row.get("repository")):
                raise StagingRejected("Invalid activation inventory entry")
            repo = row["repository"]
            # Conflicting duplicate statuses must never be treated as safe.
            if repo in statuses:
                raise StagingRejected("Duplicate activation inventory entry")
            statuses[repo] = row.get("status", "")

        rejected: dict[str, int] = {}
        audit = self.root / "logs" / "staging-rejections.jsonl"
        if audit.exists() or audit.is_symlink():
            if audit.is_symlink() or not audit.is_file() or audit.stat().st_size > 200_000:
                raise StagingRejected("Unsafe staging rejection audit")
            for line in audit.read_text("utf-8").splitlines():
                try:
                    row = json.loads(line)
                except (TypeError, ValueError):
                    continue
                if (isinstance(row, dict) and row.get("status") == "STAGING_REJECTED"
                        and _valid_repository(row.get("repository"))
                        and type(row.get("timestamp")) is int):
                    repo = row["repository"]
                    rejected[repo] = max(rejected.get(repo, 0), row["timestamp"])

        removed = 0
        cutoff = time.time() - 24 * 3600
        for stage in sorted(staging.iterdir(), key=lambda p: p.lstat().st_mtime):
            if removed >= max_directories:
                break
            if stage.is_symlink() or (hasattr(stage, "is_junction") and stage.is_junction()):
                raise StagingRejected("Unsafe staging directory link")
            if not stage.is_dir() or stage.stat().st_mtime >= cutoff:
                continue
            parts = stage.name.split("__")
            if (len(parts) != 2
                    or not _valid_repository("/".join(parts))):
                continue
            repository = "/".join(parts)
            status = statuses.get(repository)
            if status not in (None, "QUARANTINED"):
                continue
            verified = self.root / "verified" / stage.name
            _checked_path(verified)
            rejected_only = (status is None and not verified.exists()
                             and rejected.get(repository, 0) >= stage.stat().st_mtime)
            if status != "QUARANTINED" and not rejected_only:
                continue
            _checked_path(stage)
            for directory, dirs, files in os.walk(stage, followlinks=False):
                for name in dirs + files:
                    item = Path(directory) / name
                    if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
                        raise StagingRejected("Unsafe staged evidence link")
            shutil.rmtree(stage)
            removed += 1
        return removed

    def prune_permanent_evolution_artifacts(self, *, max_packages: int = 12,
                                            defer_locked_terminal: bool = False) -> int:
        """Bounded removal of terminal runtimes and needless source archives.

        Never remove ACTIVE, unclassified or recoverable quarantines, signed
        receipts, manifests, Owner data, or a package with ambiguous inventory
        state. Only exact terminal reasons recorded in trusted local metadata
        permit deletion; links/junctions fail closed before any removal.
        """
        if type(max_packages) is not int or not 1 <= max_packages <= 12:
            raise StagingRejected("Invalid permanent-artifact prune budget")
        self.last_prune_deferred: set[str] = set()
        verified = self.root / "verified"
        runtime = self.root / "runtime"
        _prune_path(verified, "PruneVerifiedRootUnsafe")
        if not verified.is_dir():
            raise WorkspacePruneError("PruneVerifiedRootUnsafe", "Unsafe verified root")
        _prune_path(runtime, "PruneRuntimeRootUnsafe")
        if runtime.exists():
            if not runtime.is_dir():
                raise WorkspacePruneError("PruneRuntimeRootUnsafe", "Unsafe evolution runtime root")
        _prune_path(self.active, "PruneInventoryUnsafe")
        if (self.active.is_symlink() or not self.active.is_file()
                or self.active.stat().st_size > 200_000):
            raise WorkspacePruneError("PruneInventoryUnsafe", "Unsafe active inventory for quota cleanup")
        try:
            inventory = json.loads(self.active.read_text("utf-8"))
        except (OSError, ValueError) as exc:
            raise WorkspacePruneError("PruneInventoryReadFailed", "Inventory read failed") from exc
        if (not isinstance(inventory, dict)
                or inventory.get("schema") != "aura.external-capabilities.v1"
                or not isinstance(inventory.get("active"), list)
                or len(inventory["active"]) > self.max_items):
            raise WorkspacePruneError("PruneInventoryInvalid", "Untrusted activation inventory for quota cleanup")
        statuses = {}
        for row in inventory["active"]:
            if (not isinstance(row, dict)
                    or not _valid_repository(row.get("repository"))):
                raise WorkspacePruneError("PruneInventoryInvalid", "Invalid quota cleanup inventory row")
            repository = row["repository"]
            if repository in statuses:
                raise WorkspacePruneError("PruneInventoryInvalid", "Duplicate quota cleanup inventory row")
            statuses[repository] = row
        terminal_reasons = {
            "PythonVersionIncompatible", "StagingRejected",
            "PROVIDER_FAILED_OR_REVOKED", "OWNER_REVOKED",
        }
        removed = 0
        attempts = 0
        for package in sorted(verified.iterdir()):
            if attempts >= max_packages:
                break
            if package.is_symlink() or (hasattr(package, "is_junction") and package.is_junction()):
                raise WorkspacePruneError("PruneVerifiedPackageLink", "Unsafe verified package link")
            if not package.is_dir() or package.name.count("__") != 1:
                continue
            repository = package.name.replace("__", "/")
            if not _valid_repository(repository):
                continue
            row = statuses.get(repository, {})
            if row.get("status") == "ACTIVE":
                continue
            terminal = (
                row.get("status") == "REVOKED"
                or (row.get("status") == "QUARANTINED"
                    and row.get("reason_code") in terminal_reasons)
            )
            marker = package / "local-windows-quarantined.json"
            if marker.exists() or marker.is_symlink():
                _prune_path(marker, "PruneQuarantinePathUnsafe")
                if not marker.is_file() or marker.stat().st_size > 2048:
                    raise WorkspacePruneError("PruneQuarantineInvalid", "Unsafe local quarantine record for cleanup")
                try:
                    reason = json.loads(marker.read_text("utf-8"))
                except (OSError, ValueError) as exc:
                    raise WorkspacePruneError("PruneQuarantineReadFailed", "Quarantine read failed") from exc
                if not isinstance(reason, dict):
                    raise WorkspacePruneError("PruneQuarantineInvalid", "Invalid local quarantine record for cleanup")
                if (reason.get("status") == "QUARANTINED"
                        and reason.get("reason_code") in terminal_reasons):
                    terminal = True
            if not terminal:
                continue

            current = runtime / package.name
            archive = package / "source.zip"
            # Validate BOTH candidates before deleting EITHER. Unknown links
            # cannot be used to redirect cleanup beyond evolution storage.
            _prune_path(current, "PruneTerminalRuntimeUnsafe")
            _prune_path(archive, "PruneTerminalArchiveUnsafe")
            if current.exists():
                if not current.is_dir():
                    raise WorkspacePruneError("PruneTerminalRuntimeUnsafe", "Invalid terminal runtime directory")
                for folder, dirs, files in os.walk(current, followlinks=False, onerror=_raise_walk_error):
                    for name in dirs + files:
                        child = Path(folder) / name
                        if child.is_symlink() or (
                            hasattr(child, "is_junction") and child.is_junction()
                        ):
                            raise WorkspacePruneError("PruneTerminalRuntimeLink", "Unsafe terminal runtime link")
            if archive.exists():
                if not archive.is_file():
                    raise WorkspacePruneError("PruneTerminalArchiveUnsafe", "Unsafe terminal source archive")
            changed = False
            if current.is_dir() or (archive.is_file() and archive.stat().st_size >= _MIB):
                attempts += 1
            try:
                if current.is_dir():
                    shutil.rmtree(current)
                    changed = True
                # Preserve small source archives for postmortem review.
                if archive.is_file() and archive.stat().st_size >= _MIB:
                    archive.unlink()
                    changed = True
            except OSError as exc:
                # The independent account need not have DELETE rights on Core
                # runtime files. A terminal package remains denied and can be
                # reclaimed later by its authorized owner. Do not chmod, take
                # ownership, follow links, or retry with elevated credentials.
                locked = isinstance(exc, PermissionError) or getattr(exc, "winerror", None) in {32, 33}
                if not defer_locked_terminal or not locked:
                    raise WorkspacePruneError("PruneTerminalDeleteFailed", "Terminal artifact deletion failed") from exc
                self.last_prune_deferred.add(repository)
                continue
            if changed:
                removed += 1
                self.audit(action="quota_prune", repository=repository, result="RECLAIMED")
        return removed

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
        if not _valid_repository(repository):
            raise StagingRejected("Invalid GitHub repository identity")
        key = repository.replace("/", "__")
        stage = self.root / "staging" / key
        verified = self.root / "verified" / key
        _checked_path(stage)
        _checked_path(verified)
        if not verified.exists():
            if len(list((self.root / "verified").iterdir())) >= self.max_items:
                raise StagingRejected("Evolution package count quota reached")
        # Reclaim only terminal external artifacts before the combined quota
        # check. Active or temporarily quota-deferred packages remain intact.
        self.prune_permanent_evolution_artifacts()
        if self._usage() + additional_bytes > self.max_bytes:
            raise StagingRejected("Evolution storage size quota reached")
        return stage, verified


def _validated_files(
    archive: bytes | io.BufferedIOBase, *,
    max_archive_bytes: int | None = None,
    summary: dict[str, object] | None = None,
) -> tuple[dict[str, bytes], str, int]:
    """Inspect untrusted ZIP metadata first; retain only bounded review source.

    Large archives and passive assets are never extracted to the filesystem.
    Paths, compressed sizes, special-file types and the total inflated size
    are validated even for members outside the source-review subset.
    """
    if isinstance(archive, bytes):
        archive_size = len(archive)
        source = io.BytesIO(archive)
    else:
        archive.seek(0, os.SEEK_END)
        archive_size = archive.tell()
        archive.seek(0)
        source = archive
    if archive_size > (max_archive_bytes if max_archive_bytes is not None else _archive_budget()):
        raise StagingRejected("Archive download exceeds maximum byte budget")
    try:
        z = zipfile.ZipFile(source)
    except (zipfile.BadZipFile, OSError) as exc:
        raise StagingRejected("Invalid repository ZIP archive") from exc

    result: dict[str, bytes] = {}
    seen: set[str] = set()
    roots: set[str] = set()
    skipped_binaries = 0
    skipped_non_source = 0
    total = 0
    retained = 0
    max_members = _archive_member_budget()
    max_file = _file_budget()
    max_extracted = _extracted_budget()
    with z:
        infos = z.infolist()
        if len(infos) > max_members:
            raise StagingRejected("Archive has too many members")
        for info in infos:
            raw = info.filename
            if ("\\" in raw or "//" in raw or not _FILE.fullmatch(raw)
                    or raw.startswith("/") or raw.startswith(".")):
                raise StagingRejected("Unsafe ZIP entry name")
            segments = PurePosixPath(raw).parts
            if len(segments) == 1 and info.is_dir():
                continue
            if len(segments) < 2 or any(part in _DENIED_PARTS for part in segments):
                raise StagingRejected("Unsafe ZIP path segments")
            roots.add(segments[0])
            if len(roots) != 1:
                raise StagingRejected("Archive has multiple source roots")
            parts = segments[1:]
            if (any(part.rstrip(" .") != part or
                    part.split(".")[0].lower() in _WIN_RESERVED
                    for part in parts)):
                raise StagingRejected("Windows-unsafe archive filename")
            rel = "/".join(parts)
            if len(rel) > 200 or len(parts) > 12:
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
            if info.file_size > 100 * max(1024, info.compress_size):
                raise StagingRejected("ZIP compression ratio exceeded")
            total += info.file_size
            if total > max_extracted:
                raise StagingRejected("Expanded repository budget exceeded")

            suffix = PurePosixPath(rel.lower()).suffix
            if suffix in _EXECUTABLE_SUFFIXES:
                # Never silently drop executable payloads, even under docs/.
                raise StagingRejected("Executable or suspicious archive content rejected")
            if suffix in _SKIP_SCRIPT_SUFFIXES:
                # A script suffix alone is not proof the content is inert text.
                # Reject PE/ELF/Mach-O or unmarked NUL-laden binary masquerades
                # (UTF-16 BOM is allowed for genuine Windows helper text).
                try:
                    with z.open(info) as handle:
                        header = handle.read(min(info.file_size, 4096))
                except (RuntimeError, OSError, zipfile.BadZipFile, EOFError) as exc:
                    raise StagingRejected("Archive helper cannot be safely inspected") from exc
                looks_utf16 = header.startswith((bytes.fromhex("fffe"), bytes.fromhex("feff")))
                if (header.startswith((b"MZ", bytes.fromhex("7f454c46"),
                                      bytes.fromhex("cffaedfe"), bytes.fromhex("feedfacf")))
                        or (bytes([0]) in header and not looks_utf16)):
                    raise StagingRejected("Executable or suspicious archive content rejected")
                skipped_non_source += 1
                continue
            passive = suffix in (_PASSIVE_ASSET_SUFFIXES | _PASSIVE_SUFFIXES)
            ignored = (suffix in _SKIP_SCRIPT_SUFFIXES
                       or any(part.casefold() in _SKIP_DIRS for part in parts[:-1])
                       or rel.lower().endswith((".min.js", ".min.mjs", ".min.cjs")))
            if passive or ignored:
                skipped_binaries += int(passive)
                skipped_non_source += int(not passive)
                continue
            if info.file_size > max_file:
                # Oversized active source cannot be inspected safely.
                raise StagingRejected("ZIP file budget exceeded")
            if (len(result) >= _MAX_STATIC_FILES
                    or retained + info.file_size > _MAX_STATIC_BYTES):
                raise StagingRejected("Static source inspection budget exceeded")
            try:
                data = z.read(info)
            except (RuntimeError, OSError, zipfile.BadZipFile, EOFError) as exc:
                raise StagingRejected("Archive entry cannot be safely read") from exc
            if len(data) != info.file_size:
                raise StagingRejected("Archive member size mismatch")
            try:
                readable = data.decode("utf-8", "strict")
            except UnicodeDecodeError as exc:
                if suffix in _SOURCE_SUFFIXES:
                    raise StagingRejected("Non-UTF8 active source requires manual review") from exc
                skipped_binaries += 1
                continue
            if "\x00" in readable:
                if suffix in _SOURCE_SUFFIXES:
                    raise StagingRejected("Binary active source requires manual review")
                skipped_binaries += 1
                continue
            result[rel] = data
            retained += len(data)

    if not result:
        raise StagingRejected("No eligible source files found")
    readmes = [
        data.decode("utf-8")
        for path, data in result.items()
        if "/" not in path and path.lower() in
        ("readme.md", "readme.rst", "readme.txt")
    ]
    if not readmes or not any(re.search(
        r"(?i)\b(?:offline|fully local|runs? locally|self.hosted|"
        r"(?:no|zero) api[ _-]?keys?|without (?:an? )?api[ _-]?key|"
        r"required no external credentials)\b", readme,
    ) for readme in readmes):
        raise StagingRejected("Local/no-paid-key README evidence required")
    entrypoints = sorted(
        path for path in result if path.rsplit("/", 1)[-1].lower() in _ENTRY
    )
    if not entrypoints:
        entrypoints = sorted(
            path for path, data in result.items()
            if PurePosixPath(path).suffix.lower() in _SOURCE_SUFFIXES
            and ("FastMCP" in data.decode("utf-8") or
                 "MCPServer" in data.decode("utf-8") or
                 "@modelcontextprotocol/sdk" in data.decode("utf-8"))
        )
    if not entrypoints:
        raise StagingRejected("No supported Python stdio MCP entrypoint")

    detected: set[str] = set()
    patterns = {
        "subprocess": r"\bsubprocess\b",
        "httpx": r"\bhttpx\b",
        "requests": r"\brequests\b",
        "urllib": r"\burllib\b",
        "aiohttp": r"\baiohttp\b",
        "sqlite3": r"\bsqlite3\b",
        "pathlib": r"\bpathlib\b",
        "os.getenv": r"\bos\.getenv\s*\(",
        "FastMCP": r"\bFastMCP\b",
        "MCP SDK": r"@modelcontextprotocol/sdk",
    }
    for path, data in result.items():
        lower = path.lower()
        if _PLATFORM.search(path):
            raise StagingRejected("Platform-specific macOS/MLX candidate")
        readable = data.decode("utf-8")
        if "/" not in path and lower in ("readme.md", "pyproject.toml", "package.json"):
            if _PLATFORM.search(readable):
                raise StagingRejected("Unsupported macOS-only integration")
            if _PAID.search(readable):
                raise StagingRejected("Mandatory paid API or external credential signature detected")
        if PurePosixPath(lower).suffix in _SOURCE_SUFFIXES:
            if _UNSAFE.search(readable):
                raise StagingRejected("Static risk: obfuscated execution or reverse shell detected")
            for capability, expression in patterns.items():
                if re.search(expression, readable):
                    detected.add(capability)
    # A pyproject name, Django server.py, go.mod, or package.json alone is
    # insufficient evidence of a Python stdio MCP implementation. Keep the
    # snapshot inert and reject it before verified/owner approval promotion.
    python_sources = [
        data for path, data in result.items()
        if PurePosixPath(path).suffix.lower() == ".py"
    ]
    sdk_markers = (
        b"FastMCP", b"MCPServer", b"mcp.server",
        b"from fastmcp import", b"import fastmcp",
    )
    if not python_sources or not any(
        marker in data for data in python_sources for marker in sdk_markers
    ):
        raise StagingRejected("No supported Python stdio MCP entrypoint")

    if summary is not None:
        summary["detected_capabilities"] = sorted(detected)
        summary["skipped_non_source"] = skipped_non_source
        summary["archive_members"] = len(infos)
        summary["expanded_bytes"] = total
    return result, entrypoints[0], skipped_binaries

class GitHubStagingMCPProvider:
    """Registered Gateway-only tool: immutable-source snapshot and static audit."""

    def __init__(self, *, workspace: EvolutionWorkspace,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.workspace = workspace
        self._transport = transport
        self._token = _github_token()

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
                    max_bytes: int, sink: io.BufferedIOBase | None = None) -> bytes | None:
        # Explicit redirect handling instead of follow_redirects=True avoids
        # leaking API tokens or contacting an attacker-chosen third-party host.
        try:
            for redirect_count in range(3):
                parsed = urlsplit(url)
                if (parsed.scheme != "https"
                        or parsed.hostname not in {"api.github.com", "codeload.github.com"}
                        or parsed.username is not None or parsed.password is not None
                        or parsed.port not in (None, 443)):
                    raise StagingRejected("GitHub archive redirect origin denied")
                headers = {
                    "User-Agent": "AURA-Evolution-Static-Review/1.0",
                    "Accept": ("application/vnd.github+json"
                               if parsed.hostname == "api.github.com" else "application/zip"),
                }
                if parsed.hostname == "api.github.com" and self._token is not None:
                    headers["Authorization"] = "Bearer " + self._token
                async with client.stream("GET", url, headers=headers) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location or redirect_count >= 2:
                            raise StagingRejected("GitHub archive redirect limit exceeded")
                        url = urljoin(url, location)
                        continue
                    if response.status_code != 200:
                        raise StagingRejected("GitHub archive/metadata unavailable or rate limited")
                    data = bytearray() if sink is None else None
                    received = 0
                    async for chunk in response.aiter_bytes():
                        received += len(chunk)
                        if received > max_bytes:
                            raise StagingRejected("GitHub download byte budget exceeded")
                        if sink is None:
                            data.extend(chunk)
                        else:
                            sink.write(chunk)
                    if sink is not None:
                        sink.flush()
                        sink.seek(0)
                        return None
                    return bytes(data)
            raise StagingRejected("GitHub archive redirect limit exceeded")
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
        if not _valid_repository(repository):
            raise StagingRejected("Invalid GitHub repository")
        # Spool large ZIP downloads outside the checkout (not into RAM).
        with tempfile.TemporaryFile(mode="w+b", dir=self.workspace.root / "staging") as archive_sink:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=httpx.Timeout(15.0, connect=5.0),
                follow_redirects=False, trust_env=False,
            ) as client:
                metadata = json.loads(await self._read(
                    client, f"https://api.github.com/repos/{repository}",
                    max_bytes=GITHUB_RESPONSE_MAX_BYTES,
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
                from aura_core.evolution.self_discovery import _SAAS
                if (_PLATFORM.search(description) or _PAID.search(description)
                        or _SAAS.search(repository + " " + description)):
                    raise StagingRejected("Paid SaaS or macOS-only candidate rejected")
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
                download_budget = _archive_budget()
                await self._read(
                    client, f"https://codeload.github.com/{repository}/zip/{sha}",
                    max_bytes=download_budget, sink=archive_sink,
                )
            scan_summary: dict[str, object] = {}
            files, entrypoint, skipped_binaries = _validated_files(
                archive_sink, max_archive_bytes=download_budget, summary=scan_summary,
            )
            archive_size = archive_sink.seek(0, os.SEEK_END)
            archive_sink.seek(0)
            hasher = hashlib.sha256()
            while block := archive_sink.read(1024 * 1024):
                hasher.update(block)
            archive_sha = hasher.hexdigest()
            stage, verified = self.workspace.reserve(
                repository, archive_size * 2 + sum(map(len, files.values())) + 8192
            )
            # No existing evidence is overwritten. The on-disk manifest only
            # points to pinned bytes, not a runnable command or trusted receipt.
            if verified.exists():
                old_manifest = verified / "aura-capability-manifest.json"
                if old_manifest.is_symlink():
                    raise StagingRejected("Unsafe cached static manifest path")
                if old_manifest.is_file() and old_manifest.stat().st_size <= 16_000:
                    old = json.loads(old_manifest.read_text("utf-8"))
                    if old.get("source_sha256") == archive_sha and old.get("repository") == repository:
                        # A cached manifest alone cannot restore a pruned ZIP.
                        # Only the freshly downloaded, validated, SHA-matching
                        # original may be restored; never rewrite signed proof.
                        cached_zip = verified / "source.zip"
                        if (cached_zip.is_symlink()
                                or (cached_zip.exists() and not cached_zip.is_file())):
                            raise StagingRejected("Unsafe cached source archive path")
                        repair = not cached_zip.is_file()
                        if not repair:
                            current_hash = hashlib.sha256()
                            with cached_zip.open("rb") as stream:
                                while chunk := stream.read(1024 * 1024):
                                    current_hash.update(chunk)
                            repair = current_hash.hexdigest() != archive_sha
                        if repair:
                            handle, temporary = tempfile.mkstemp(
                                prefix=".archive-repair-", dir=verified,
                            )
                            try:
                                archive_sink.seek(0)
                                with os.fdopen(handle, "wb") as target:
                                    shutil.copyfileobj(archive_sink, target, 1024 * 1024)
                                    target.flush()
                                    os.fsync(target.fileno())
                                os.replace(temporary, cached_zip)
                            finally:
                                if os.path.exists(temporary):
                                    os.unlink(temporary)
                        self.workspace.audit(action="stage_cached", repository=repository,
                                             result="STATIC_REVIEW_ONLY")
                        return old
                raise StagingRejected("Existing verified package requires independent review")
            if stage.exists():
                raise StagingRejected("Existing staged package requires independent review")
            stage_tmp = Path(tempfile.mkdtemp(prefix=".staging-", dir=self.workspace.root / "staging"))
            verified_tmp = Path(tempfile.mkdtemp(prefix=".verified-", dir=self.workspace.root / "verified"))
            try:
                archive_sink.seek(0)
                with (stage_tmp / "source.zip").open("wb") as target:
                    shutil.copyfileobj(archive_sink, target, 1024 * 1024)
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
                    "skipped_binaries": skipped_binaries,
                    "skipped_non_source": scan_summary["skipped_non_source"],
                    "archive_members": scan_summary["archive_members"],
                    "expanded_bytes": scan_summary["expanded_bytes"],
                    "detected_capabilities": scan_summary["detected_capabilities"],
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
                archive_sink.seek(0)
                with (verified_tmp / "source.zip").open("wb") as target:
                    shutil.copyfileobj(archive_sink, target, 1024 * 1024)
                (verified_tmp / "aura-capability-manifest.json").write_text(
                    json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8",
                )
                stage_tmp.rename(stage)
                verified_tmp.rename(verified)
                self.workspace.audit(action="stage_verified", repository=repository,
                                     result="OWNER_REVIEW_REQUIRED")
                return report
            finally:
                if stage_tmp.exists():
                    shutil.rmtree(stage_tmp)
                if verified_tmp.exists():
                    shutil.rmtree(verified_tmp)
