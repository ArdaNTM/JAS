"""Read-only public GitHub discovery through the existing MCP Gateway.

Never download executable code, install packages, grant permissions or prepare
an executable provider. Repository README text is untrusted source evidence.
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
from urllib.parse import urlencode
from uuid import uuid4

from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.mcp.gateway import MCPGatewayRequest

logger = logging.getLogger(__name__)
LICENSES = frozenset({"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC"})
TOPICS = (
    ("mcp server local tools", "MCP araç entegrasyonu"),
    ("python offline ai assistant", "Yerel yapay zekâ"),
    ("open source local automation python", "Masaüstü ve otomasyon"),
)
REPO_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SELF_HOSTED = re.compile(
    r"\b(?:offline|self.hosted|self.host|runs locally|local.llm|local model|"
    r"ollama|without api keys?|no api key|no cloud required)\b", re.I,
)
PAID_REQUIRED = re.compile(
    r"(?:required|mandatory|must|needs?)\s+(?:an?\s+)?(?:paid|commercial|"
    r"subscription|openai.api.key|anthropic.api.key|cloud api)|"
    r"(?:openai_api_key|anthropic_api_key|stripe_secret_key)|"
    r"(?:paid|commercial)\s+(?:api|plan|subscription)\s+required", re.I,
)


class DiscoveryDenied(RuntimeError):
    """The configured Gateway/network boundary did not authorize the read."""


def eligible_public_repo(repo: object, readme: str) -> bool:
    """Conservative metadata and README screen; not a license audit."""
    if not isinstance(repo, dict) or not isinstance(readme, str):
        return False
    full = repo.get("full_name")
    if (not isinstance(full, str) or REPO_NAME.fullmatch(full) is None
            or any(part in {".", ".."} for part in full.split("/"))
            or repo.get("private") is not False
            or repo.get("archived") is True or repo.get("fork") is True):
        return False
    if repo.get("html_url") != "https://github.com/" + full:
        return False
    license_info = repo.get("license")
    if not isinstance(license_info, dict) or license_info.get("spdx_id") not in LICENSES:
        return False
    evidence = readme[:16000]
    summary = str(repo.get("description") or "")[:600]
    if (len(evidence) < 40 or PAID_REQUIRED.search(evidence)
            or PAID_REQUIRED.search(summary) or not SELF_HOSTED.search(evidence)):
        return False
    return True


class SelfDiscoveryEngine:
    """Rate-limited, persistent review candidates only; no activation path."""

    def __init__(self, *, gateway, database_path: Path,
                 principal_id: str = "local_owner", interval_seconds: int = 3600):
        if gateway is None or not 900 <= interval_seconds <= 86400:
            raise ValueError("Gateway and interval [900, 86400] are mandatory")
        path = Path(database_path).expanduser()
        if not path.is_absolute() or path.is_symlink() or path.parent.is_symlink():
            raise ValueError("Discovery database must be an absolute, non-symlink path")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.gateway = gateway
        self.principal_id = principal_id
        self.database_path = path
        self.interval_seconds = interval_seconds
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        with sqlite3.connect(path, timeout=10) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS evolution_proposals (
                id TEXT PRIMARY KEY, full_name TEXT NOT NULL UNIQUE,
                url TEXT NOT NULL, license_id TEXT NOT NULL,
                summary TEXT NOT NULL, capability TEXT NOT NULL,
                readme_sha256 TEXT NOT NULL, discovered_at INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status = 'awaiting_owner_review')
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS evolution_discovery_meta (
                key TEXT PRIMARY KEY, value INTEGER NOT NULL
            )""")

    def _next_allowed(self) -> int:
        with sqlite3.connect(self.database_path, timeout=10) as db:
            row = db.execute(
                "SELECT value FROM evolution_discovery_meta WHERE key='next_allowed'"
            ).fetchone()
        return int(row[0]) if row else 0

    def _set_next_allowed(self, timestamp: int) -> None:
        with sqlite3.connect(self.database_path, timeout=10) as db:
            db.execute(
                "INSERT OR REPLACE INTO evolution_discovery_meta VALUES (?,?)",
                ("next_allowed", timestamp),
            )

    def proposals(self, limit: int = 20) -> list[dict[str, object]]:
        with sqlite3.connect(self.database_path, timeout=10) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                """SELECT id, full_name, url, license_id, summary, capability,
                          discovered_at, status FROM evolution_proposals
                   ORDER BY discovered_at DESC, full_name ASC LIMIT ?""",
                (max(1, min(limit, 50)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def status(self) -> dict[str, object]:
        with sqlite3.connect(self.database_path, timeout=10) as db:
            count = db.execute("SELECT count(*) FROM evolution_proposals").fetchone()[0]
        return {"count": count, "next_allowed": self._next_allowed(),
                "mode": "read_only_owner_review", "authorization_granted": False,
                "execution_performed": False}

    @staticmethod
    def _unwrap(result: object) -> dict:
        """Decode the existing MCP fetch tool's structured JSON response."""
        if getattr(result, "isError", False):
            raise DiscoveryDenied("Research MCP returned a tool error")
        data = getattr(result, "structured_content", None)
        if data is None:
            data = getattr(result, "structuredContent", None)
        if data is None and isinstance(result, dict):
            data = result
        if data is None:
            contents = getattr(result, "content", ())
            if not contents:
                raise DiscoveryDenied("Research MCP returned no content")
            first = getattr(contents[0], "text", None)
            if not isinstance(first, str) or len(first) > 60000:
                raise DiscoveryDenied("Research MCP returned invalid content")
            data = json.loads(first)
        if not isinstance(data, dict):
            raise DiscoveryDenied("Research MCP returned an invalid object")
        if data.get("status_code") != 200:
            raise DiscoveryDenied("GitHub public API unavailable or rate limited")
        url = data.get("url")
        if not isinstance(url, str) or not url.startswith("https://api.github.com/"):
            raise DiscoveryDenied("Research fetch redirected outside GitHub API")
        raw = data.get("content")
        if not isinstance(raw, str) or len(raw) > 50000:
            raise DiscoveryDenied("GitHub response is missing or exceeds bounds")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise DiscoveryDenied("GitHub response was not JSON object")
        return payload

    async def _fetch_api(self, url: str) -> dict:
        if not url.startswith("https://api.github.com/") or len(url) > 500:
            raise DiscoveryDenied("Only pinned public GitHub API reads are allowed")
        response = await asyncio.wait_for(self.gateway.invoke(MCPGatewayRequest(
            request_id=str(uuid4()), principal_id=self.principal_id,
            capability_id="internet.fetch", operation_id="internet.fetch",
            tool_name="fetch", resource_scope="public-web", risk_level=RiskLevel.LOW,
            arguments={"url": url},
        )), timeout=40)
        if response.decision is not AuthorizationDecision.ALLOW:
            raise DiscoveryDenied("MCP Gateway denied GitHub discovery")
        return self._unwrap(response.result)

    async def run_once(self) -> dict[str, object]:
        """Manual/periodic triggers share a durable cooldown and bounded budget."""
        async with self._lock:
            now = int(time.time())
            if now < self._next_allowed():
                return {**self.status(), "items": self.proposals(10),
                        "added": 0, "note": "cooldown"}
            # Commit cooldown before network requests, including across restarts.
            self._set_next_allowed(now + self.interval_seconds)
            topic, capability = TOPICS[(now // self.interval_seconds) % len(TOPICS)]
            search_url = "https://api.github.com/search/repositories?" + urlencode({
                "q": topic + " archived:false fork:false",
                "sort": "stars", "order": "desc", "per_page": 8,
            })
            added = 0
            note = "ok"
            try:
                data = await self._fetch_api(search_url)
                repos = data.get("items", [])
                if not isinstance(repos, list):
                    raise DiscoveryDenied("Invalid repository search results")
                readme_checks = 0
                for repo in repos[:8]:
                    if not isinstance(repo, dict):
                        continue
                    full_name = repo.get("full_name")
                    if (not isinstance(full_name, str) or REPO_NAME.fullmatch(full_name) is None
                            or any(x in {".", ".."} for x in full_name.split("/"))):
                        continue
                    if (repo.get("license") or {}).get("spdx_id") not in LICENSES:
                        continue
                    if readme_checks >= 3:
                        break
                    readme_checks += 1
                    try:
                        readme_payload = await self._fetch_api(
                            "https://api.github.com/repos/" + full_name + "/readme"
                        )
                        if readme_payload.get("encoding") != "base64":
                            continue
                        encoded = readme_payload.get("content")
                        if not isinstance(encoded, str) or len(encoded) > 48000:
                            continue
                        readme = base64.b64decode(encoded, validate=False).decode(
                            "utf-8", errors="replace"
                        )
                        if not eligible_public_repo(repo, readme):
                            continue
                    except (DiscoveryDenied, ValueError, OSError, UnicodeError):
                        continue
                    digest = hashlib.sha256(full_name.encode()).hexdigest()
                    summary = re.sub(r"[\x00-\x1f]+", " ", str(
                        repo.get("description") or "Local open-source tool"
                    ))[:400]
                    with sqlite3.connect(self.database_path, timeout=10) as db:
                        cursor = db.execute(
                            """INSERT OR IGNORE INTO evolution_proposals
                               (id, full_name, url, license_id, summary, capability,
                                readme_sha256, discovered_at, status)
                               VALUES (?,?,?,?,?,?,?,?,?)""",
                            (digest, full_name, repo["html_url"],
                             repo["license"]["spdx_id"], summary,
                             capability, hashlib.sha256(readme.encode()).hexdigest(),
                             now, "awaiting_owner_review"),
                        )
                        added += cursor.rowcount
            except (DiscoveryDenied, OSError, ValueError, asyncio.TimeoutError) as exc:
                logger.warning("Review-only GitHub discovery unavailable: %s", exc)
                note = "gateway_or_github_unavailable"
            return {**self.status(), "items": self.proposals(10),
                    "added": added, "note": note}

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="aura-self-discovery")

    async def _loop(self) -> None:
        # Defer initial scan to leave user-triggered scans immediate.
        while True:
            await asyncio.sleep(self.interval_seconds)
            try:
                await self.run_once()
            except Exception:
                logger.exception("Read-only discovery cycle failed")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
