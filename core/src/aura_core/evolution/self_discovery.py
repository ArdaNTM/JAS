"""Bounded GitHub discovery, using an explicitly authorized MCP Gateway call.

No repository is cloned, imported, executed or registered. Public metadata is
untrusted evidence, never an Owner approval or a permission policy.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.gateway import MCPGatewayRequest
from aura_core.mcp.mcp_provider import MCPTool

logger = logging.getLogger("aura_core.evolution.self_discovery")

CAPABILITY_ID = "github.repository.search"
TOOL_NAME = "search_open_source"
SCOPE = "public-github"
# Fixed decoded response budget per GitHub public JSON request (DoS bounded).
GITHUB_RESPONSE_MAX_BYTES = 2 * 1024 * 1024
SEARCH_PER_PAGE = 6
MAX_SEARCH_PAGE = 5
CATALOG_CAPABILITY = "public.mcp.catalog.search"
CATALOG_TOOL = "search_catalog"
CATALOG_SCOPE = "public-mcp-catalog"
PYPI_SEEDS = ("mcp-server-memory", "mcp-server-time", "mcp-server-fetch",
              "mcp-server-git", "mcp-server-sqlite", "fastmcp")
REGISTRY_TERMS = ("memory", "filesystem", "sqlite", "git", "local", "python")
PERMITTED_LICENSES = frozenset({
    "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC",
})
# Fixed, operator-owned allowlist; never accept LLM/user-supplied URLs.
# Target small/local MCP implementations rather than repeating broad top-star
# results. Each manual scan tries at most two queries to bound GitHub API use.
QUERIES = (
    '"FastMCP" "mcp.tool" language:Python size:<25000 archived:false stars:>5',
    '"from mcp.server.fastmcp import FastMCP" language:Python size:<25000 archived:false stars:>5',
    '"from fastmcp import FastMCP" language:Python size:<25000 archived:false stars:>5',
    '"fastmcp" server language:Python size:<25000 archived:false stars:>5',
    '"mcp" server language:Python size:<25000 archived:false stars:>5',
    '"modelcontextprotocol" server language:Python size:<25000 archived:false stars:>5',
    '"mcp-server" sqlite language:Python size:<25000 archived:false stars:>5',
    '"mcp-server" memory language:Python size:<25000 archived:false stars:>5',
)
MAX_QUERIES_PER_MANUAL_SCAN = 2
_REPO = re.compile(r"^[A-Za-z0-9_.-]{1,80}/[A-Za-z0-9_.-]{1,100}$")


def _valid_repository(value: object) -> bool:
    if not isinstance(value, str) or not _REPO.fullmatch(value):
        return False
    return all(part not in (".", "..") and not part.endswith(".")
               for part in value.split("/"))
_SAAS = re.compile(
    r"(?i)\b(?:bright[ -]?data|basecamp|shodan|virus[ -]?total|"
    r"mandatory (?:saas|cloud|subscription)|"
    r"requires? (?:a )?(?:paid )?(?:api key|cloud subscription))\b"
)
_LOCAL_TOOLS = re.compile(
    r"(?i)\b(?:mcp[ -]?server|fastmcp|sqlite|filesystem|"
    r"playwright|git|memory|fetch|local|offline|stdio)\b"
)


_NO_KEY_EVIDENCE = re.compile(
    r"(?i)\b(?:zero\s+api[\s_-]*keys?|no\s+api[\s_-]*keys?|"
    r"without\s+(?:an?\s+)?api[\s_-]*key|fully\s+offline)\b"
)


def _local_rank(repository: str, description: str, stars: int) -> int:
    """Deterministic local/no-keys score, independent of popularity alone."""
    text = repository + " " + description
    return (sum(10 for _ in _LOCAL_TOOLS.finditer(text))
            + (20 if _NO_KEY_EVIDENCE.search(text) else 0)
            + min(8, max(0, stars) // 200))


def _python_mcp_priority(repository: str, description: str) -> int:
    """Rank Python FastMCP evidence ahead of legacy Go/Node/TS proposals.

    Metadata is advisory, never activation authority. Static archive screening
    and the signed Owner / independent MCP handshake remain mandatory.
    """
    value = (repository + " " + description).casefold()
    if "fastmcp" in value or (
        "python" in value and ("mcp" in value or "stdio" in value)
    ):
        return 0
    if re.search(r"(?i)\\b(?:golang|go[- ]based|node(?:\\.js)?|typescript|rust|django)\\b", value):
        return 2
    return 1


def _size_tier(size_kb: int | None) -> int:
    # GitHub Search API's size is KiB, a rough project-size indicator;
    # unknown values are neutral, never fabricated as small.
    if size_kb is None:
        return 1
    if size_kb <= 15_000:
        return 0
    if size_kb <= 60_000:
        return 2
    return 3


_UNSUPPORTED_HOST = re.compile(
    r"\b(?:mlx|apple.silicon|macos.only|darwin|swift|xcode)\b",
    re.IGNORECASE,
)
_NEGATIVE = re.compile(
    r"(?:requires?|mandatory|must\s+(?:provide|set|configure))"
    r".{0,70}(?:paid\s+api|api[\s_-]?key|cloud\s+subscription)"
    r"|(?:OPENAI_API_KEY|ANTHROPIC_API_KEY|STRIPE_SECRET_KEY)"
    r"|(?:paid\s+(?:plan|subscription)\s+required)",
    re.IGNORECASE,
)
_POSITIVE = re.compile(
    r"\b(?:offline|fully local|runs? locally|local inference|"
    r"without (?:an? )?api[\s_-]?key|no api[\s_-]?key(?: required)?|"
    r"self.hosted|ollama)\b",
    re.IGNORECASE,
)


class DiscoveryUnavailable(RuntimeError):
    pass


def _safe_text(value: object, limit: int = 180) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(c for c in value if c.isprintable()).strip()[:limit]


def _github_token() -> str | None:
    """Optional local credential; never log or send to untrusted redirects."""
    # Environment variables are intentionally limited to these two explicit
    # GitHub identities. No credential is ever placed in a codeload redirect.
    def valid(value: str) -> bool:
        return bool(value) and len(value) <= 255 and not any(c.isspace() for c in value)

    for key in ("GITHUB_TOKEN", "GH_TOKEN"):
        token = os.environ.get(key, "").strip()
        if valid(token):
            return token
    token = ""
    if not token:
        executable = shutil.which("gh")
        if executable:
            try:
                result = subprocess.run(
                    [executable, "auth", "token"], capture_output=True,
                    text=True, check=False, timeout=3,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if result.returncode == 0:
                    token = result.stdout.strip()
            except (OSError, subprocess.TimeoutExpired):
                pass
    if not token or len(token) > 255 or any(c.isspace() for c in token):
        return None
    return token


class PublicGitHubDiscoveryMCPProvider:
    """Fixed-origin public GETs only. Must be invoked via MCPGateway grant."""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport
        self._token = _github_token()

    async def list_tools(self) -> tuple[MCPTool, ...]:
        return (MCPTool(
            name=TOOL_NAME,
            description="Search bounded public open-source GitHub repositories",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string", "enum": list(QUERIES)},
                               "page": {"type": "integer", "minimum": 1,
                                        "maximum": MAX_SEARCH_PAGE}},
                "required": ["query"],
                "additionalProperties": False,
            },
        ),)

    async def _get(self, client: httpx.AsyncClient, path: str,
                   params: dict[str, object] | None = None) -> dict:
        # The caller only passes path constants and regex-validated repo names.
        url = "https://api.github.com" + path
        try:
            headers = {
                "Accept": "application/vnd.github+json",
                "User-Agent": "AURA-JAS-Local-Discovery/1.0",
            }
            if self._token is not None:
                headers["Authorization"] = "Bearer " + self._token
            async with client.stream("GET", url, params=params, headers=headers) as response:
                if response.status_code in (403, 429):
                    raise DiscoveryUnavailable("GitHub public API rate limit reached (403/429)")
                if response.status_code == 404:
                    raise FileNotFoundError("GitHub README/repository not found")
                if response.status_code != 200:
                    raise DiscoveryUnavailable("GitHub public API unavailable")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(data) + len(chunk) > GITHUB_RESPONSE_MAX_BYTES:
                        raise DiscoveryUnavailable("GitHub response exceeds 2 MiB budget")
                    data.extend(chunk)
            payload = json.loads(data)
            if not isinstance(payload, dict):
                raise DiscoveryUnavailable("Invalid GitHub public API response")
            return payload
        except (httpx.RequestError, ValueError) as exc:
            raise DiscoveryUnavailable("GitHub public API connection/response failed") from exc

    async def call_tool(self, name: str,
                        arguments: dict | None = None) -> dict[str, object]:
        grant = current_dispatch()
        if (grant is None or grant.capability_id != CAPABILITY_ID
                or grant.tool_name != TOOL_NAME or grant.principal_id != "local_owner"):
            raise PermissionError("GitHub discovery requires an authorized MCPGateway dispatch")
        if (name != TOOL_NAME or not isinstance(arguments, dict)
                or set(arguments) not in ({"query"}, {"query", "page"})):
            raise ValueError("Invalid GitHub discovery operation")
        query = arguments["query"]
        page = arguments.get("page", 1)
        if not isinstance(query, str) or query not in QUERIES:
            raise ValueError("Unapproved GitHub search query")
        if type(page) is not int or not 1 <= page <= MAX_SEARCH_PAGE:
            raise ValueError("Unapproved bounded GitHub search page")

        async with httpx.AsyncClient(
            transport=self._transport, timeout=httpx.Timeout(12.0, connect=5.0),
            follow_redirects=False, trust_env=False,
        ) as client:
            search = await self._get(client, "/search/repositories", {
                "q": query, "per_page": SEARCH_PER_PAGE, "sort": "stars",
                "order": "desc", "page": page,
            })
            rows = search.get("items")
            if not isinstance(rows, list):
                raise DiscoveryUnavailable("GitHub search result missing items")
            candidates: list[dict[str, str]] = []
            for row in rows[:SEARCH_PER_PAGE]:
                if not isinstance(row, dict):
                    continue
                full_name = row.get("full_name")
                stars = row.get("stargazers_count")
                if type(stars) is not int or not 0 <= stars <= 2_000_000_000:
                    continue
                license_obj = row.get("license")
                license_id = (license_obj.get("spdx_id")
                              if isinstance(license_obj, dict) else None)
                if (not _valid_repository(full_name)
                        or license_id not in PERMITTED_LICENSES
                        or row.get("private") is True
                        or row.get("archived") is True
                        or row.get("fork") is True):
                    continue
                description_hint = str(row.get("description") or "")
                # GitHub's primary language is untrusted metadata, but explicit
                # non-Python results should not consume a Python stdio queue
                # slot; existing catalog rows still undergo ZIP screening.
                language = row.get("language")
                if isinstance(language, str) and language.casefold() in {
                    "go", "rust", "javascript", "typescript"
                }:
                    continue
                if (_UNSUPPORTED_HOST.search(description_hint)
                        or _SAAS.search(full_name + " " + description_hint)):
                    continue
                try:
                    # No README -> no claim that the repo is genuinely local and
                    # does not require a commercial API key. Reject conservatively.
                    readme = await self._get(client, "/repos/" + full_name + "/readme")
                    if readme.get("encoding") != "base64":
                        continue
                    encoded = readme.get("content")
                    if not isinstance(encoded, str) or len(encoded) > 90_000:
                        continue
                    content = base64.b64decode(encoded, validate=False)[:60_000]
                    description = content.decode("utf-8", "replace")
                    if (not _POSITIVE.search(description)
                            or _NEGATIVE.search(description)
                            or _UNSUPPORTED_HOST.search(description)
                            or _SAAS.search(description)):
                        continue
                except FileNotFoundError:
                    # An individual candidate without README is not a valid
                    # local/free tool, but must not abort the entire search.
                    continue
                except DiscoveryUnavailable:
                    # Query-level failure is reported to the engine; other
                    # independent queries can still succeed.
                    raise
                except (ValueError, TypeError, OSError):
                    continue
                size_kb = row.get("size")
                if type(size_kb) is not int or not 0 <= size_kb <= 2_000_000_000:
                    size_kb = None
                candidates.append({
                    "repository": full_name,
                    "url": "https://github.com/" + full_name,
                    "description": _safe_text(row.get("description")) or
                                   "Local open-source MCP / AI integration candidate",
                    "license": license_id,
                    "stars": stars,
                    "size_kb": size_kb,
                    "capability_hint": (
                        "MCP server integration" if "mcp" in query
                        else "local inference and automation"
                    ),
                    "evidence": "GitHub license SPDX + README local/no-required-key filter",
                    "local_rank": _local_rank(full_name, description_hint, stars),
                })
                # Inspect up to SEARCH_PER_PAGE entries before ranking.
            candidates.sort(
                key=lambda entry: (
                    0 if entry["local_rank"] >= 10 else 1,
                    _size_tier(entry["size_kb"]),
                    -entry["local_rank"], -entry["stars"], entry["repository"],
                )
            )
        return {
            "items": candidates[:SEARCH_PER_PAGE],
            "source": "github.com/search/repositories",
            "verification": "metadata_and_readme_only_not_code_audit",
        }



class PublicCatalogDiscoveryMCPProvider(PublicGitHubDiscoveryMCPProvider):
    """Read-only MCP Registry / PyPI discovery behind one explicit Gateway tool.

    Registry and PyPI metadata are *untrusted hints*. Before enqueueing, an
    exact GitHub repository, permissive SPDX license, and a README showing
    local/no-required-key operation must be corroborated via api.github.com.
    No dynamic URL, redirect, package installation, code or Owner grant is used.
    """

    async def list_tools(self) -> tuple[MCPTool, ...]:
        return (MCPTool(
            name=CATALOG_TOOL, description="Search fixed free MCP registry and PyPI indexes",
            input_schema={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "enum": ["registry", "pypi"]},
                    "slot": {"type": "integer", "minimum": 0, "maximum": 5},
                },
                "required": ["source"], "additionalProperties": False,
            },
        ),)

    @staticmethod
    def _github_repository(value: object) -> str | None:
        if not isinstance(value, str) or len(value) > 256:
            return None
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or parsed.hostname != "github.com"
                or parsed.port not in (None, 443) or parsed.username or parsed.password
                or parsed.query or parsed.fragment):
            return None
        path = parsed.path.removesuffix(".git").strip("/")
        return path if _valid_repository(path) else None

    async def _index(self, client: httpx.AsyncClient, *, source: str, slot: int) -> dict:
        if source == "registry":
            url = "https://registry.modelcontextprotocol.io/v0.1/servers"
            params = {"search": REGISTRY_TERMS[slot], "version": "latest", "limit": 8}
        else:
            url = "https://pypi.org/pypi/" + PYPI_SEEDS[slot] + "/json"
            params = None
        try:
            async with client.stream("GET", url, params=params, headers={
                "Accept": "application/json",
                "User-Agent": "AURA-JAS-Local-Catalog/1.0",
            }) as response:
                if response.status_code in (403, 429):
                    raise DiscoveryUnavailable(source + " rate limit reached (403/429)")
                if response.status_code == 404:
                    return {}
                if response.status_code != 200:
                    raise DiscoveryUnavailable(source + " public catalog unavailable")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(data) + len(chunk) > 262_144:
                        raise DiscoveryUnavailable(source + " index exceeds 256 KiB")
                    data.extend(chunk)
            payload = json.loads(data)
            if not isinstance(payload, dict):
                raise DiscoveryUnavailable("Invalid public catalog JSON response")
            return payload
        except (httpx.RequestError, ValueError) as exc:
            raise DiscoveryUnavailable(source + " public catalog connection failed") from exc

    async def call_tool(self, name: str,
                        arguments: dict | None = None) -> dict[str, object]:
        grant = current_dispatch()
        if (grant is None or grant.capability_id != CATALOG_CAPABILITY
                or grant.tool_name != CATALOG_TOOL or grant.principal_id != "local_owner"):
            raise PermissionError("Public catalog requires MCPGateway authorization")
        if (name != CATALOG_TOOL or not isinstance(arguments, dict)
                or set(arguments) not in ({"source"}, {"source", "slot"})):
            raise ValueError("Unsupported public catalog operation")
        source, slot = arguments.get("source"), arguments.get("slot", 0)
        if source not in ("registry", "pypi") or type(slot) is not int or not 0 <= slot < 6:
            raise ValueError("Unapproved catalog source or slot")

        async with httpx.AsyncClient(
            transport=self._transport, timeout=httpx.Timeout(15.0, connect=5.0),
            follow_redirects=False, trust_env=False,
        ) as client:
            payload = await self._index(client, source=source, slot=slot)
            hints: list[tuple[str, str]] = []
            if source == "registry":
                rows = payload.get("servers")
                if not isinstance(rows, list):
                    rows = []
                for row in rows[:8]:
                    if not isinstance(row, dict):
                        continue
                    server = row.get("server", row)
                    if not isinstance(server, dict):
                        continue
                    repository = server.get("repository")
                    url = repository.get("url") if isinstance(repository, dict) else None
                    name = self._github_repository(url)
                    if name is not None:
                        hints.append((name, _safe_text(server.get("description"))))
            else:
                info = payload.get("info")
                if isinstance(info, dict):
                    values = " ".join(str(info.get(key) or "")[:500]
                                      for key in ("name", "keywords", "summary")).casefold()
                    if "mcp" in values or "fastmcp" in values:
                        urls = info.get("project_urls")
                        sources = list(urls.values())[:10] if isinstance(urls, dict) else []
                        sources.append(info.get("home_page"))
                        for url in sources:
                            name = self._github_repository(url)
                            if name is not None:
                                hints.append((name, _safe_text(info.get("summary"))))
                                break

            candidates: list[dict[str, object]] = []
            for name, hint in hints[:4]:
                try:
                    repo = await self._get(client, "/repos/" + name)
                    if (repo.get("full_name") != name or repo.get("private") is True
                            or repo.get("archived") is True or repo.get("fork") is True
                            or (repo.get("language") or "").casefold()
                            in {"go", "rust", "typescript", "javascript"}):
                        continue
                    license_info = repo.get("license")
                    license_id = license_info.get("spdx_id") if isinstance(license_info, dict) else None
                    if license_id not in PERMITTED_LICENSES:
                        continue
                    readme = await self._get(client, "/repos/" + name + "/readme")
                    encoded = readme.get("content")
                    if (readme.get("encoding") != "base64"
                            or not isinstance(encoded, str) or len(encoded) > 90_000):
                        continue
                    text = base64.b64decode(encoded, validate=False)[:60_000].decode(
                        "utf-8", "replace",
                    )
                    if (not _POSITIVE.search(text) or _NEGATIVE.search(text)
                            or _SAAS.search(text + " " + name)
                            or _UNSUPPORTED_HOST.search(text)):
                        continue
                    stars = repo.get("stargazers_count")
                    if type(stars) is not int or not 0 <= stars <= 2_000_000_000:
                        stars = 0
                    size = repo.get("size")
                    if type(size) is not int or not 0 <= size <= 2_000_000_000:
                        size = None
                    candidates.append({
                        "repository": name, "url": "https://github.com/" + name,
                        "description": _safe_text(repo.get("description")) or hint,
                        "license": license_id, "stars": stars, "size_kb": size,
                        "capability_hint": "Python FastMCP (" + source + ")",
                        "evidence": source + " hint + GitHub SPDX and local README",
                    })
                except FileNotFoundError:
                    continue
            return {
                "items": candidates[:3], "source": source,
                "verification": "github_license_and_local_readme_only",
            }


class SelfDiscoveryEngine:
    """Durable review-only EvolutionProposal inventory; never an installer."""

    def __init__(self, *, gateway, db_path: str | Path,
                 principal_id: str = "local_owner",
                 interval_seconds: int = 3600, workspace=None,
                 auto_stage: bool = False):
        self.gateway = gateway
        if principal_id != "local_owner":
            raise PermissionError("Only the configured local Owner may run discovery")
        self.principal_id = principal_id
        self.workspace = workspace
        self.auto_stage = bool(auto_stage and workspace is not None)
        # Composed Kernel callback only; never model-supplied and no default
        # authorization. Trusted delegated manager rechecks Owner + attestor.
        self.on_verified = None
        self.interval_seconds = max(1800, min(int(interval_seconds), 86400))
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._cycle = 0
        self._last_error = ""
        self._source_health: dict[str, dict[str, object]] = {
            name: {"state": "IDLE", "successful_queries": 0,
                   "failed_queries": 0, "reason": ""}
            for name in ("github", "registry", "pypi")
        }
        path = Path(db_path).expanduser()
        if not path.is_absolute() or path.is_symlink():
            raise ValueError("Discovery database must use an absolute non-symlink path")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir():
            raise ValueError("Discovery database path must be a file")
        self._db_path = path
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS evolution_proposals (
                proposal_id TEXT PRIMARY KEY,
                repository TEXT NOT NULL UNIQUE,
                url TEXT NOT NULL,
                description TEXT NOT NULL,
                license TEXT NOT NULL,
                capability_hint TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending_owner_review',
                created_at REAL NOT NULL,
                stars INTEGER
            )""")
            # Existing PR #168 SQLite files must migrate without losing queued
            # proposals. Old entries have unknown, never fabricated stars.
            columns = {row[1] for row in db.execute("PRAGMA table_info(evolution_proposals)")}
            if "stars" not in columns:
                db.execute("ALTER TABLE evolution_proposals ADD COLUMN stars INTEGER")
            if "size_kb" not in columns:
                db.execute("ALTER TABLE evolution_proposals ADD COLUMN size_kb INTEGER")
            if "package_status" not in columns:
                db.execute("ALTER TABLE evolution_proposals ADD COLUMN package_status TEXT")
            if "source_sha256" not in columns:
                db.execute("ALTER TABLE evolution_proposals ADD COLUMN source_sha256 TEXT")
            if "package_error" not in columns:
                db.execute("ALTER TABLE evolution_proposals ADD COLUMN package_error TEXT")
            if "stage_attempts" not in columns:
                db.execute(
                    "ALTER TABLE evolution_proposals ADD COLUMN stage_attempts INTEGER "
                    "NOT NULL DEFAULT 0"
                )
            if "stage_retry_version" not in columns:
                # Version 1 grants one re-evaluation of legacy limit/false-
                # positive failures regardless of old attempt count.
                db.execute(
                    "ALTER TABLE evolution_proposals ADD COLUMN stage_retry_version "
                    "INTEGER NOT NULL DEFAULT 0"
                )
            db.execute("""CREATE TABLE IF NOT EXISTS discovery_history (
                cycle INTEGER PRIMARY KEY,
                recorded_at INTEGER NOT NULL,
                query_count INTEGER NOT NULL,
                new_proposals INTEGER NOT NULL,
                staged_count INTEGER NOT NULL,
                status TEXT NOT NULL
            )""")
            # Persist the query cursor across Windows daemon restarts; old
            # discovery_history rows are reused without resetting proposals.
            self._cycle = int(db.execute(
                "SELECT COALESCE(MAX(cycle),0) FROM discovery_history"
            ).fetchone()[0])

    def _connect(self):
        return sqlite3.connect(str(self._db_path), timeout=5)

    def proposals(self, limit: int = 20) -> list[dict[str, object]]:
        count = max(1, min(int(limit), 50))
        with self._connect() as db:
            rows = db.execute(
                "SELECT proposal_id,repository,url,description,license,"
                "capability_hint,status,created_at,stars,size_kb,package_status,source_sha256,"
                "package_error,stage_attempts "
                "FROM evolution_proposals ORDER BY created_at DESC LIMIT ?", (count,)
            ).fetchall()
        proposals = []
        for row in rows:
            record = dict(zip(
                ("proposal_id", "repository", "url", "description", "license",
                 "capability_hint", "status", "created_at", "stars", "size_kb",
                 "package_status", "source_sha256", "package_error", "stage_attempts"), row
            ))
            # A non-executable integration blueprint is review data only.
            # Never infer a runnable entrypoint from arbitrary GitHub README.
            record["integration_blueprint"] = {
                "source": record["url"],
                "suggested_transport": "stdio_pending_owner_validation",
                "entrypoint": None,
                "next_step": "manual source and license audit; independent sandbox attestation",
                "activation": "blocked_until_signed_owner_receipt",
            }
            proposals.append(record)
        return proposals

    def count(self) -> int:
        with self._connect() as db:
            return int(db.execute("SELECT COUNT(*) FROM evolution_proposals").fetchone()[0])

    def queued_count(self) -> int:
        """Outstanding static-staging queue; ready packages have a separate count."""
        with self._connect() as db:
            return int(db.execute(
                "SELECT COUNT(*) FROM evolution_proposals "
                "WHERE package_status IS NULL OR package_status IN ('pending','Queued')"
            ).fetchone()[0])

    def status(self) -> dict[str, object]:
        return {
            "enabled": self._task is not None and not self._task.done(),
            "mode": "review_only",
            "proposal_count": self.count(),
            "cycles": self._cycle,
            "last_error": self._last_error,
            "source_health": {name: dict(item) for name, item in self._source_health.items()},
            "tool_execution": False,
            "code_modified": False,
            "requires_owner_webauthn": True,
            "requires_independent_attestation": True,
            "auto_stage_enabled": self.auto_stage,
            "verified_static_count": self.static_ready_count(),
        }

    def static_ready_count(self) -> int:
        with self._connect() as db:
            return int(db.execute(
                "SELECT COUNT(*) FROM evolution_proposals "
                "WHERE package_status='READY_FOR_OWNER_REVIEW'"
            ).fetchone()[0])

    async def _stage_pending(self, *, continuous: bool = False,
                             on_progress=None) -> dict[str, object]:
        report: dict[str, object] = {
            "attempted": 0, "staged_count": 0, "verified_count": 0, "rejected": [],
        }
        if not self.auto_stage:
            return report
        from aura_core.evolution.external_staging import (
            CAPABILITY as STAGE_CAPABILITY, TOOL as STAGE_TOOL,
            staging_scope, _archive_budget,
        )
        with self._connect() as db:
            # A READY database label is not static proof if its pinned ZIP was
            # pruned or modified. Requeue metadata only; the normal Gateway
            # staging path must download and validate the archive again.
            ready = db.execute(
                "SELECT repository,source_sha256 FROM evolution_proposals "
                "WHERE status='pending_owner_review' "
                "AND package_status='READY_FOR_OWNER_REVIEW'"
            ).fetchall()
            for repository, expected_sha in ready:
                if not _valid_repository(repository):
                    continue
                archive = (self.workspace.root / "verified" /
                           repository.replace("/", "__") / "source.zip")
                stale = archive.is_symlink() or not archive.is_file()
                if not stale:
                    try:
                        if (not isinstance(expected_sha, str)
                                or not re.fullmatch(r"[0-9a-f]{64}", expected_sha)
                                or archive.stat().st_size > _archive_budget()):
                            stale = True
                        else:
                            digest = hashlib.sha256()
                            with archive.open("rb") as stream:
                                while chunk := stream.read(1024 * 1024):
                                    digest.update(chunk)
                            stale = digest.hexdigest() != expected_sha
                    except OSError:
                        stale = True
                if stale:
                    db.execute(
                        "UPDATE evolution_proposals SET package_status=NULL,"
                        "source_sha256=NULL,package_error=NULL "
                        "WHERE repository=? AND package_status='READY_FOR_OWNER_REVIEW'",
                        (repository,),
                    )
            rows = db.execute(
                "SELECT repository,description,stars,size_kb,package_error,package_status "
                "FROM evolution_proposals "
                "WHERE status='pending_owner_review' "
                "AND (package_status IS NULL OR package_status IN ('pending', 'Queued') "
                "OR (package_status='STAGING_REJECTED' "
                "AND stage_retry_version=0 AND package_error IN ("
                "'GitHub download byte budget exceeded',"
                "'Archive download exceeds maximum byte budget',"
                "'Expanded repository budget exceeded',"
                "'GitHub archive/metadata unavailable or rate limited',"
                "'Archive has too many members',"
                "'ZIP file budget exceeded',"
                "'Binary content is not eligible for static staging',"
                "'Static risk/paid API signature detected'"
                ")) OR (package_status='STAGING_REJECTED' "
                "AND stage_retry_version<2 AND "
                "package_error='Executable or suspicious archive content rejected')) "
                "ORDER BY CASE WHEN package_status IS NULL THEN 0 "
                "WHEN package_status IN ('pending','Queued') THEN 1 ELSE 2 END, "
                "stage_attempts, created_at LIMIT 150"
            ).fetchall()
        # Once-only migration recovery of bounded legacy failures. The new
        # scanner still rejects actual malicious code; other policy/permission
        # failures never enter this queue. No new repo required for retry.
        candidates = [
            (repository, description, stars or 0, size_kb, reason, package_status)
            for repository, description, stars, size_kb, reason, package_status in rows
            if _valid_repository(repository)
            and not _SAAS.search(repository + " " + description)
        ]
        candidates.sort(
            key=lambda row: (
                # Keep the established size-aware/local-first ordering.
                # Script false-positive retry remains lowest priority.
                1 if row[4] == "Executable or suspicious archive content rejected" else 0,
                _python_mcp_priority(row[0], row[1]),
                0 if _local_rank(row[0], row[1], row[2]) >= 10 else 1,
                _size_tier(row[3]),
                -_local_rank(row[0], row[1], row[2]),
                row[0],
            )
        )
        if continuous:
            # A full multi-source scan must drain SIX historic NULL proposals
            # per pass when available. Keep the per-cycle HTTP/staging budget
            # finite; every one still enters the existing MCPGateway boundary.
            fresh = [item for item in candidates if item[5] is None][:6]
            fresh_names = {item[0] for item in fresh}
            chosen = fresh + [
                item for item in candidates if item[0] not in fresh_names
            ][:max(0, 6 - len(fresh))]
        else:
            chosen = list(candidates[:3])
            if len(candidates) > 50 and not any(item[4] is None for item in chosen):
                # Preserve the historic size-aware local-first manual scan.
                fresh = next((item for item in candidates[3:] if item[4] is None), None)
                if fresh is not None:
                    chosen[-1] = fresh
        for repository, _, _, _, _, _ in chosen:
            report["attempted"] += 1
            try:
                response = await asyncio.wait_for(self.gateway.invoke(MCPGatewayRequest(
                    request_id=str(uuid4()), principal_id=self.principal_id,
                    capability_id=STAGE_CAPABILITY, operation_id=STAGE_CAPABILITY,
                    resource_scope=staging_scope(self.workspace),
                    risk_level=RiskLevel.MEDIUM,
                    tool_name=STAGE_TOOL, arguments={"repository": repository},
                )), timeout=12)
                if response.decision is not AuthorizationDecision.ALLOW:
                    raise PermissionError(
                        "MCPGateway denied inert external staging for local_owner"
                    )
                manifest = response.result
                if (not isinstance(manifest, dict)
                        or manifest.get("repository") != repository
                        or manifest.get("status") != "READY_FOR_OWNER_REVIEW"
                        or manifest.get("sandbox_attested") is not False
                        or manifest.get("activation_performed") is not False
                        or manifest.get("execution_allowed") is not False):
                    raise ValueError("Staging returned invalid static review proof")
                digest = manifest.get("source_sha256")
                if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise ValueError("Source SHA-256 missing from static report")
                # The staging tool's manifest is still untrusted. Never treat
                # it as authorization to execute or register an MCP provider.
                with self._connect() as db:
                    db.execute(
                        "UPDATE evolution_proposals SET package_status=?,source_sha256=?,"
                        "package_error=NULL,stage_attempts=stage_attempts+1,"
                        "stage_retry_version=2 WHERE repository=?",
                        ("READY_FOR_OWNER_REVIEW", digest, repository),
                    )
                report["staged_count"] += 1
                report["verified_count"] += 1
            except (PermissionError, ValueError, RuntimeError,
                    OSError, asyncio.TimeoutError) as exc:
                reason = _safe_text(str(exc), 160) or type(exc).__name__
                logger.warning("Static staging rejected %s: %s", repository, reason)
                unsupported = "No supported Python stdio MCP entrypoint" in reason
                with self._connect() as db:
                    db.execute(
                        "UPDATE evolution_proposals SET package_status=?,"
                        "package_error=?,stage_attempts=stage_attempts+1,"
                        "stage_retry_version=2 WHERE repository=?",
                        ("UNSUPPORTED_RUNTIME" if unsupported else "STAGING_REJECTED",
                         reason, repository),
                    )
                report["rejected"].append({
                    "repository": repository, "reason": reason,
                })
                self.workspace.audit_rejection(repository, reason)
            finally:
                if on_progress is not None:
                    # Core-owned synchronous display callback; a HUD failure
                    # must never change Gateway staging authorization/results.
                    try:
                        on_progress(1)
                    except Exception:
                        logger.warning("Staging progress observer failed")
        return report

    def history(self, limit: int = 25) -> list[dict[str, object]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT cycle, recorded_at, query_count, new_proposals,"
                "staged_count, status FROM discovery_history ORDER BY cycle DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [dict(zip(
            ("cycle", "recorded_at", "query_count", "new_proposals",
             "staged_count", "status"), row
        )) for row in rows]

    def _history_record(self, *, query_count: int, saved: int,
                        staged: int, status: str) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO discovery_history "
                "(cycle,recorded_at,query_count,new_proposals,staged_count,status) "
                "VALUES (?,?,?,?,?,?)",
                (self._cycle, int(time.time()), query_count, saved, staged, status),
            )

    def _store_public_candidates(
        self, result: dict, seen: set[str],
    ) -> int:
        """Deduplicate bounded candidate metadata, never treat it as approval."""
        saved = 0
        with self._connect() as db:
            known = {r[0] for r in db.execute(
                "SELECT repository FROM evolution_proposals"
            )}
            eligible = []
            for row in result.get("items", [])[:SEARCH_PER_PAGE]:
                if not isinstance(row, dict):
                    continue
                name, license_id, stars = (
                    row.get("repository"), row.get("license"), row.get("stars"),
                )
                size_kb = row.get("size_kb")
                if type(size_kb) is not int or not 0 <= size_kb <= 2_000_000_000:
                    size_kb = None
                if (not _valid_repository(name)
                        or license_id not in PERMITTED_LICENSES
                        or row.get("url") != "https://github.com/" + name
                        or type(stars) is not int or not 0 <= stars <= 2_000_000_000):
                    continue
                eligible.append((row, name, stars, size_kb))
            eligible.sort(key=lambda item: (
                item[1] in known,
                _size_tier(item[3]),
                -_local_rank(item[1], _safe_text(item[0].get("description")), item[2]),
                item[1],
            ))
            for row, name, stars, size_kb in eligible[:3]:
                seen.add(name)
                proposal_id = hashlib.sha256(name.casefold().encode()).hexdigest()[:24]
                try:
                    cursor = db.execute(
                        "INSERT OR IGNORE INTO evolution_proposals "
                        "(proposal_id,repository,url,description,license,capability_hint,"
                        "created_at,stars,size_kb) VALUES (?,?,?,?,?,?,?,?,?)",
                        (proposal_id, name, row["url"],
                         _safe_text(row.get("description")),
                         row["license"], _safe_text(row.get("capability_hint"), 100),
                         time.time(), stars, size_kb),
                    )
                    saved += cursor.rowcount
                    if cursor.rowcount == 0:
                        db.execute(
                            "UPDATE evolution_proposals SET stars=?,"
                            "size_kb=COALESCE(?,size_kb) "
                            "WHERE proposal_id=? AND repository=?",
                            (stars, size_kb, proposal_id, name),
                        )
                except (TypeError, ValueError, KeyError):
                    continue
        return saved

    async def run_once(self, *, full_scan: bool = False,
                       multi_source: bool = False,
                       on_progress=None) -> dict[str, object]:
        async with self._lock:
            # A manual scan covers two *rotating* query slots, not the
            # entire expanding allowlist (bounded public GitHub API use).
            # _cycle was restored from persisted discovery_history.
            query_count = MAX_QUERIES_PER_MANUAL_SCAN if full_scan else 1
            indexes = tuple(
                (self._cycle + offset) % len(QUERIES)
                for offset in range(query_count)
            )
            self._cycle += len(indexes)
            def publish_progress(scanned: int) -> None:
                if on_progress is not None and scanned > 0:
                    try:
                        on_progress(scanned)
                    except Exception:
                        # Observability never modifies security or scan outcome.
                        logger.warning("Discovery progress observer failed")

            seen: set[str] = set()
            saved = 0
            successful_queries = 0
            failed_queries: list[dict[str, str]] = []
            health: dict[str, dict[str, object]] = {
                name: {"state": "IDLE", "successful_queries": 0,
                       "failed_queries": 0, "reason": ""}
                for name in ("github", "registry", "pypi")
            }

            def observe(source: str, failure: str = "") -> None:
                item = health[source]
                key = "failed_queries" if failure else "successful_queries"
                item[key] = int(item[key]) + 1
                if failure:
                    # Public API errors are data, never authority or raw tracebacks.
                    item["reason"] = _safe_text(failure, 120)
                successes, errors = item["successful_queries"], item["failed_queries"]
                item["state"] = ("DEGRADED" if successes and errors
                                 else "OK" if successes else "UNAVAILABLE")

            try:
                for index in indexes:
                    # Network, rate-limit, and provider errors affect only this
                    # independent public query. Permission denials are not
                    # availability failures: they remain fail-closed.
                    try:
                        response = await self.gateway.invoke(MCPGatewayRequest(
                            request_id=str(uuid4()), principal_id=self.principal_id,
                            capability_id=CAPABILITY_ID, operation_id=CAPABILITY_ID,
                            resource_scope=SCOPE, risk_level=RiskLevel.LOW,
                            tool_name=TOOL_NAME, arguments=(
                                {"query": QUERIES[index],
                                 "page": ((self._cycle // len(QUERIES)) % MAX_SEARCH_PAGE) + 1}
                                if multi_source else {"query": QUERIES[index]}
                            ),
                        ))
                        if response.decision is not AuthorizationDecision.ALLOW:
                            raise PermissionError("MCPGateway denied GitHub discovery")
                        result = response.result
                        if (not isinstance(result, dict)
                                or not isinstance(result.get("items"), list)):
                            raise DiscoveryUnavailable(
                                "Discovery provider returned invalid evidence"
                            )
                    except PermissionError:
                        raise
                    except (DiscoveryUnavailable, RuntimeError,
                            asyncio.TimeoutError, OSError) as exc:
                        reason = _safe_text(str(exc), 160) or "GitHub query unavailable"
                        failed_queries.append({
                            "query": QUERIES[index], "reason": reason,
                        })
                        observe("github", reason)
                        continue
                    successful_queries += 1
                    observe("github")

                    saved += self._store_public_candidates(result, seen)
                    publish_progress(len(result["items"]))

                if multi_source:
                    # Additional discovery is not a privilege escalation. Each
                    # fixed-origin index is a separate authorized Gateway call;
                    # the staging Gateway still independently verifies GitHub.
                    slot = (self._cycle // len(QUERIES)) % len(PYPI_SEEDS)
                    for source in ("registry", "pypi"):
                        try:
                            response = await asyncio.wait_for(
                                self.gateway.invoke(MCPGatewayRequest(
                                    request_id=str(uuid4()), principal_id=self.principal_id,
                                    capability_id=CATALOG_CAPABILITY,
                                    operation_id=CATALOG_CAPABILITY,
                                    resource_scope=CATALOG_SCOPE, risk_level=RiskLevel.LOW,
                                    tool_name=CATALOG_TOOL,
                                    arguments={"source": source, "slot": slot},
                                )), timeout=45,
                            )
                            if response.decision is not AuthorizationDecision.ALLOW:
                                raise PermissionError("MCPGateway denied public catalog discovery")
                            result = response.result
                            if not isinstance(result, dict) or not isinstance(result.get("items"), list):
                                raise DiscoveryUnavailable("Invalid catalog discovery evidence")
                            successful_queries += 1
                            observe(source)
                            saved += self._store_public_candidates(result, seen)
                            publish_progress(len(result["items"]))
                        except PermissionError:
                            raise
                        except (DiscoveryUnavailable, RuntimeError, OSError,
                                asyncio.TimeoutError) as exc:
                            reason = _safe_text(str(exc), 160) or source + " unavailable"
                            failed_queries.append({"query": source, "reason": reason})
                            observe(source, reason)

                # Even with a rate-limited search, a previously validated
                # catalog can supply up to three inert staging candidates.
                # PermissionEngine/MCPGateway still authorizes each download.
                research_crosscheck = "not_requested"
                if saved and os.getenv("AURA_DISCOVERY_USE_RESEARCH_MCP", "0") == "1":
                    first = self.proposals(1)
                    if first:
                        try:
                            check = await asyncio.wait_for(self.gateway.invoke(
                                MCPGatewayRequest(
                                    request_id=str(uuid4()), principal_id=self.principal_id,
                                    capability_id="internet.search", operation_id="internet.search",
                                    resource_scope="public-web", risk_level=RiskLevel.LOW,
                                    tool_name="search",
                                    arguments={"query": first[0]["repository"] +
                                               " local open-source documentation"},
                                )
                            ), timeout=12.0)
                            research_crosscheck = (
                                "gateway_queried" if check.decision is AuthorizationDecision.ALLOW
                                else "gateway_denied"
                            )
                        except Exception:
                            research_crosscheck = "unavailable"
                staging_report = await self._stage_pending(
                    continuous=bool(full_scan and multi_source),
                    on_progress=publish_progress,
                )
                staged_count = staging_report["staged_count"]
                newly_activated: list[str] = []
                if staging_report["verified_count"] and self.on_verified is not None:
                    try:
                        newly_activated = await self.on_verified()
                    except Exception:
                        # External provider startup never disrupts discovery.
                        newly_activated = []
                # Preserve fail-closed 429 behavior for an empty catalog;
                # an existing queue is a useful partial offline outcome.
                if (not multi_source and not successful_queries
                        and failed_queries and not staging_report["attempted"]):
                    raise DiscoveryUnavailable(
                        "GitHub discovery failed for all queries: " +
                        failed_queries[0]["reason"]
                    )
                # Continuous scans persist partial-source health even if all
                # remote services are temporarily unavailable. Existing NULL
                # queue records must remain eligible for Gateway staging.
                self._source_health = health
                # Only show repositories actually returned by this live scan.
                # Historical queued entries are available via the list endpoint.
                current = [record for record in self.proposals(50)
                           if record["repository"] in seen]
                self._last_error = ""
                self._history_record(
                    query_count=len(indexes) + (2 if multi_source else 0), saved=saved, staged=staged_count,
                    status="PARTIAL" if failed_queries else "COMPLETE",
                )
                return {
                    "items": current, "proposal_count": self.count(),
                    "new_count": saved, "mode": "review_only",
                    "partial": bool(failed_queries),
                    "successful_queries": successful_queries,
                    "active_sources": (["github", "registry", "pypi"] if multi_source else ["github"]),
                    "failed_queries": failed_queries,
                    "source_health": {name: dict(item) for name, item in health.items()},
                    "staged_count": staged_count,
                    "staging_attempted": staging_report["attempted"],
                    "verified_count": staging_report["verified_count"],
                    "staging_rejected": staging_report["rejected"],
                    "static_ready_count": self.static_ready_count(),
                    "owner_review_url": "http://localhost:8766/",
                    "activation_performed": bool(newly_activated),
                    "auto_activated": newly_activated,
                    "local_research_crosscheck": research_crosscheck,
                }
            except (DiscoveryUnavailable, PermissionError, OSError,
                    RuntimeError, asyncio.TimeoutError) as exc:
                self._last_error = _safe_text(str(exc), 180)
                self._source_health = health
                self._history_record(query_count=len(indexes) + (2 if multi_source else 0), saved=saved,
                                     staged=0, status="FAILED")
                raise

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._run(), name="aura-self-discovery")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception:
                # Network errors and missing permissions must never stop Core
                # or escalate to tool execution.
                logger.warning("Review-only self-discovery cycle failed", exc_info=True)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                pass
