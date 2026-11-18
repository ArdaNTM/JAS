"""Explicit, scoped and bounded offline archive for authorized MCP fetch results.

No URL is fetched in this module. Search-engine and fetched page text are
untrusted stored data and must not grant runtime or policy authority.
"""
from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from aura_core.kernel.permissions import AuthorizationDecision


def _scope(principal_id: str) -> str:
    if (type(principal_id) is not str or not principal_id.strip()
            or len(principal_id) > 200
            or any(ord(ch) < 32 for ch in principal_id)):
        raise ValueError("invalid research archive principal_id")
    return principal_id


def _authorized_payload(response: Any) -> dict[str, Any]:
    if getattr(response, "decision", None) is not AuthorizationDecision.ALLOW:
        raise PermissionError("research archive requires an authorized Gateway result")
    result = getattr(response, "result", None)
    if isinstance(result, dict):
        data = result
    elif getattr(result, "isError", False):
        raise ValueError("failed provider fetch cannot be archived")
    else:
        data = getattr(result, "structuredContent", None)
    if not isinstance(data, dict):
        raise ValueError("research archive needs structured fetch content")
    return data


class SQLiteResearchArchive:
    """Local opt-in snapshots keyed by exact principal and SHA-256 identity."""

    def __init__(self, path: str | Path, *, max_chars: int = 50_000) -> None:
        if type(max_chars) is not int or not 1 <= max_chars <= 50_000:
            raise ValueError("max_chars must be 1..50000")
        self.path = str(path)
        self.max_chars = max_chars
        if self.path != ":memory:":
            Path(self.path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS research_snapshots(
                    principal_id TEXT NOT NULL,
                    archive_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY(principal_id, archive_id)
                )"""
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_research_scope_time "
                "ON research_snapshots(principal_id, created_at DESC)"
            )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=5.0)
        db.row_factory = sqlite3.Row
        return db

    def archive_fetch_result(
        self, *, principal_id: str, response: Any, consented: bool = False
    ) -> dict[str, object]:
        principal = _scope(principal_id)
        if consented is not True:
            raise PermissionError("explicit research archive consent is required")
        data = _authorized_payload(response)
        url = data.get("url")
        status = data.get("status_code")
        content_type = data.get("content_type")
        content = data.get("content")
        if (not isinstance(url, str) or not 1 <= len(url) <= 2048
                or any(ord(ch) < 33 or ord(ch) == 127 for ch in url)):
            raise ValueError("invalid source URL")
        try:
            parsed = urlsplit(url)
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("invalid source URL") from exc
        if (parsed.scheme.lower() not in {"https", "http"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None):
            raise ValueError("source URL must be HTTP(S) without credentials")
        if type(status) is not int or status != 200:
            raise ValueError("only successful HTTP 200 fetches can be archived")
        if (not isinstance(content_type, str)
                or not content_type.lower().split(";", 1)[0].strip() in
                {"text/plain", "text/html", "application/json"}):
            raise ValueError("unsupported research content type")
        if (not isinstance(content, str) or not content
                or len(content) > self.max_chars):
            raise ValueError("research content missing or exceeds limit")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        archive_id = hashlib.sha256(
            (principal + "\0" + url + "\0" + digest).encode("utf-8")
        ).hexdigest()
        with self._connect() as db:
            db.execute(
                """INSERT OR IGNORE INTO research_snapshots
                (principal_id, archive_id, url, content_type, content,
                 content_sha256, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (principal, archive_id, url, content_type, content,
                 digest, time.time()),
            )
        return {
            "archive_id": archive_id,
            "content_sha256": digest,
            "untrusted": True,
            "verified_source": False,
        }

    def get(self, *, principal_id: str, archive_id: str) -> dict[str, object] | None:
        principal = _scope(principal_id)
        if (type(archive_id) is not str or len(archive_id) != 64
                or any(ch not in "0123456789abcdef" for ch in archive_id)):
            raise ValueError("invalid archive_id")
        with self._connect() as db:
            row = db.execute(
                """SELECT archive_id, url, content_type, content,
                          content_sha256, created_at
                   FROM research_snapshots
                   WHERE principal_id = ? AND archive_id = ?""",
                (principal, archive_id),
            ).fetchone()
        if row is None:
            return None
        stored_content = row["content"]
        expected_digest = row["content_sha256"]
        if (not isinstance(stored_content, str)
                or not isinstance(expected_digest, str)
                or hashlib.sha256(stored_content.encode("utf-8")).hexdigest()
                != expected_digest):
            raise ValueError("research snapshot integrity mismatch")
        return {
            "archive_id": row["archive_id"],
            "url": row["url"],
            "content_type": row["content_type"],
            "content": row["content"],
            "content_sha256": row["content_sha256"],
            "created_at": row["created_at"],
            "untrusted": True,
            "verified_source": False,
        }


    def list_snapshots(
        self, *, principal_id: str, limit: int = 20, offset: int = 0
    ) -> tuple[dict[str, object], ...]:
        """Bounded principal-scoped archive browsing without exposing content."""
        principal = _scope(principal_id)
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("archive browse limit must be 1..50")
        if type(offset) is not int or not 0 <= offset <= 10000:
            raise ValueError("archive offset must be 0..10000")
        with self._connect() as db:
            rows = db.execute(
                """SELECT archive_id, url, content_type, content,
                          content_sha256, created_at
                   FROM research_snapshots WHERE principal_id=?
                   ORDER BY created_at DESC, archive_id ASC LIMIT ? OFFSET ?""",
                (principal, limit, offset),
            ).fetchall()
        output = []
        for row in rows:
            if hashlib.sha256(row["content"].encode("utf-8")).hexdigest() != row["content_sha256"]:
                raise ValueError("archive snapshot digest mismatch")
            output.append({
                "archive_id": row["archive_id"], "url": row["url"],
                "content_type": row["content_type"],
                "content_sha256": row["content_sha256"],
                "created_at": row["created_at"],
                "untrusted": True, "verified_source": False,
            })
        return tuple(output)

    def prune_before(
        self, *, principal_id: str, cutoff_timestamp: float,
        confirmed: bool = False,
    ) -> int:
        """Delete one principal's aged snapshots; external approval is mandatory."""
        import math
        principal = _scope(principal_id)
        if confirmed is not True:
            raise PermissionError("archive retention erasure requires approval")
        if type(cutoff_timestamp) not in (float, int) or not math.isfinite(cutoff_timestamp):
            raise ValueError("finite archive timestamp required")
        if not 0 <= cutoff_timestamp <= time.time():
            raise ValueError("cannot prune future archive snapshots")
        with self._connect() as db:
            return int(db.execute(
                "DELETE FROM research_snapshots WHERE principal_id=? AND created_at<?",
                (principal, cutoff_timestamp),
            ).rowcount)

    async def archive_governed_fetch(
        self, *, gateway: Any, request: Any, principal_id: str,
        consented: bool,
    ) -> dict[str, object]:
        """Use the REAL MCP Gateway result, not a caller-forged allow snapshot.

        Requires the application to authenticate the request's principal at its
        ingress before building MCPGatewayRequest. Provider fetch may be unsafe
        without separate network/SSRF policy and is not performed by this store.
        """
        from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
        if (not isinstance(gateway, MCPGateway) or
            not isinstance(request, MCPGatewayRequest) or
            principal_id != request.principal_id or
            type(consented) is not bool or not consented):
            raise PermissionError("authenticated principal and consented Gateway fetch required")
        response = await gateway.invoke(request)
        return self.archive_fetch_result(
            principal_id=principal_id, response=response, consented=True)

    def forget(
        self, *, principal_id: str, archive_id: str, confirmed: bool = False
    ) -> bool:
        principal = _scope(principal_id)
        if confirmed is not True:
            raise PermissionError("explicit research archive erasure confirmation required")
        if (type(archive_id) is not str or len(archive_id) != 64
                or any(ch not in "0123456789abcdef" for ch in archive_id)):
            raise ValueError("invalid archive_id")
        with self._connect() as db:
            deleted = db.execute(
                "DELETE FROM research_snapshots WHERE principal_id=? AND archive_id=?",
                (principal, archive_id),
            ).rowcount
        return deleted == 1
