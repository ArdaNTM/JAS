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
import sqlite3
import time
from pathlib import Path
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
PERMITTED_LICENSES = frozenset({
    "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC",
})
# These are operator-owned static queries, never user/LLM supplied search URLs.
QUERIES = (
    "topic:mcp-server language:Python stars:>10 archived:false",
    "topic:local-ai language:Python stars:>10 archived:false",
    "topic:ollama language:Python stars:>10 archived:false",
)
_REPO = re.compile(r"^[A-Za-z0-9_.-]{1,80}/[A-Za-z0-9_.-]{1,100}$")
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


class PublicGitHubDiscoveryMCPProvider:
    """Fixed-origin public GETs only. Must be invoked via MCPGateway grant."""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport

    async def list_tools(self) -> tuple[MCPTool, ...]:
        return (MCPTool(
            name=TOOL_NAME,
            description="Search bounded public open-source GitHub repositories",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string", "enum": list(QUERIES)}},
                "required": ["query"],
                "additionalProperties": False,
            },
        ),)

    async def _get(self, client: httpx.AsyncClient, path: str,
                   params: dict[str, object] | None = None) -> dict:
        # The caller only passes path constants and regex-validated repo names.
        url = "https://api.github.com" + path
        try:
            async with client.stream("GET", url, params=params, headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "AURA-JAS-Local-Discovery/1.0",
            }) as response:
                if response.status_code in (403, 429):
                    raise DiscoveryUnavailable("GitHub public API rate limit reached")
                if response.status_code != 200:
                    raise DiscoveryUnavailable("GitHub public API unavailable")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(data) + len(chunk) > 256_000:
                        raise DiscoveryUnavailable("GitHub response exceeds 256 KiB budget")
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
        if name != TOOL_NAME or not isinstance(arguments, dict) or set(arguments) != {"query"}:
            raise ValueError("Invalid GitHub discovery operation")
        query = arguments["query"]
        if not isinstance(query, str) or query not in QUERIES:
            raise ValueError("Unapproved GitHub search query")

        async with httpx.AsyncClient(
            transport=self._transport, timeout=httpx.Timeout(12.0, connect=5.0),
            follow_redirects=False, trust_env=False,
        ) as client:
            search = await self._get(client, "/search/repositories", {
                "q": query, "per_page": 4, "sort": "stars", "order": "desc",
            })
            rows = search.get("items")
            if not isinstance(rows, list):
                raise DiscoveryUnavailable("GitHub search result missing items")
            candidates: list[dict[str, str]] = []
            for row in rows[:4]:
                if not isinstance(row, dict):
                    continue
                full_name = row.get("full_name")
                license_obj = row.get("license")
                license_id = (license_obj.get("spdx_id")
                              if isinstance(license_obj, dict) else None)
                if (not isinstance(full_name, str) or not _REPO.fullmatch(full_name)
                        or license_id not in PERMITTED_LICENSES
                        or row.get("private") is True
                        or row.get("archived") is True
                        or row.get("fork") is True):
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
                    if not _POSITIVE.search(description) or _NEGATIVE.search(description):
                        continue
                except (DiscoveryUnavailable, ValueError, TypeError, OSError):
                    continue
                candidates.append({
                    "repository": full_name,
                    "url": "https://github.com/" + full_name,
                    "description": _safe_text(row.get("description")) or
                                   "Local open-source MCP / AI integration candidate",
                    "license": license_id,
                    "capability_hint": (
                        "MCP server integration" if "mcp" in query
                        else "local inference and automation"
                    ),
                    "evidence": "GitHub license SPDX + README local/no-required-key filter",
                })
                if len(candidates) >= 3:
                    break
        return {
            "items": candidates,
            "source": "github.com/search/repositories",
            "verification": "metadata_and_readme_only_not_code_audit",
        }


class SelfDiscoveryEngine:
    """Durable review-only EvolutionProposal inventory; never an installer."""

    def __init__(self, *, gateway, db_path: str | Path,
                 principal_id: str = "local_owner",
                 interval_seconds: int = 3600):
        self.gateway = gateway
        if principal_id != "local_owner":
            raise PermissionError("Only the configured local Owner may run discovery")
        self.principal_id = principal_id
        self.interval_seconds = max(1800, min(int(interval_seconds), 86400))
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._cycle = 0
        self._last_error = ""
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
                created_at REAL NOT NULL
            )""")

    def _connect(self):
        return sqlite3.connect(str(self._db_path), timeout=5)

    def proposals(self, limit: int = 20) -> list[dict[str, object]]:
        count = max(1, min(int(limit), 50))
        with self._connect() as db:
            rows = db.execute(
                "SELECT proposal_id,repository,url,description,license,"
                "capability_hint,status,created_at "
                "FROM evolution_proposals ORDER BY created_at DESC LIMIT ?", (count,)
            ).fetchall()
        return [
            dict(zip(("proposal_id", "repository", "url", "description", "license",
                      "capability_hint", "status", "created_at"), row))
            for row in rows
        ]

    def count(self) -> int:
        with self._connect() as db:
            return int(db.execute("SELECT COUNT(*) FROM evolution_proposals").fetchone()[0])

    def status(self) -> dict[str, object]:
        return {
            "enabled": self._task is not None and not self._task.done(),
            "mode": "review_only",
            "proposal_count": self.count(),
            "cycles": self._cycle,
            "last_error": self._last_error,
            "tool_execution": False,
            "code_modified": False,
            "requires_owner_webauthn": True,
            "requires_independent_attestation": True,
        }

    async def run_once(self) -> dict[str, object]:
        async with self._lock:
            query = QUERIES[self._cycle % len(QUERIES)]
            # One bounded query/cycle limits anonymous GitHub API consumption.
            self._cycle += 1
            try:
                response = await self.gateway.invoke(MCPGatewayRequest(
                    request_id=str(uuid4()), principal_id=self.principal_id,
                    capability_id=CAPABILITY_ID, operation_id=CAPABILITY_ID,
                    resource_scope=SCOPE, risk_level=RiskLevel.LOW,
                    tool_name=TOOL_NAME, arguments={"query": query},
                ))
                if response.decision is not AuthorizationDecision.ALLOW:
                    raise PermissionError("MCPGateway denied GitHub discovery")
                result = response.result
                if not isinstance(result, dict) or not isinstance(result.get("items"), list):
                    raise DiscoveryUnavailable("Discovery provider returned invalid evidence")
                saved = 0
                with self._connect() as db:
                    for row in result["items"][:3]:
                        if not isinstance(row, dict):
                            continue
                        name = row.get("repository")
                        license_id = row.get("license")
                        if (not isinstance(name, str) or not _REPO.fullmatch(name)
                                or license_id not in PERMITTED_LICENSES
                                or row.get("url") != "https://github.com/" + name):
                            continue
                        proposal_id = hashlib.sha256(name.casefold().encode()).hexdigest()[:24]
                        try:
                            cursor = db.execute(
                                "INSERT OR IGNORE INTO evolution_proposals "
                                "(proposal_id,repository,url,description,license,capability_hint,created_at)"
                                "VALUES (?,?,?,?,?,?,?)",
                                (proposal_id, name, row["url"],
                                 _safe_text(row.get("description")),
                                 license_id, _safe_text(row.get("capability_hint"), 100),
                                 time.time()),
                            )
                            saved += cursor.rowcount
                        except (TypeError, ValueError, KeyError):
                            continue
                self._last_error = ""
                return {
                    "items": self.proposals(10), "proposal_count": self.count(),
                    "new_count": saved, "mode": "review_only",
                    "owner_review_url": "http://localhost:8766/",
                    "activation_performed": False,
                }
            except (DiscoveryUnavailable, PermissionError, OSError,
                    RuntimeError, asyncio.TimeoutError) as exc:
                self._last_error = str(exc)[:180]
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
