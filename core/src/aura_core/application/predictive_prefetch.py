"""Opt-in predictive prefetch planner; proposes work but never executes speculative tools."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import uuid4


class PredictivePrefetchPlanner:
    def __init__(self, database_path: str | Path, *, min_observations: int = 3, max_proposals: int = 20) -> None:
        if min_observations < 2 or not 1 <= max_proposals <= 100:
            raise ValueError("invalid prefetch planner bounds")
        self.database_path = str(database_path)
        self.min_observations = min_observations
        self.max_proposals = max_proposals
        Path(self.database_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS prefetch_observations (
                principal_id TEXT NOT NULL, event_key TEXT NOT NULL, capability_id TEXT NOT NULL,
                hour_local INTEGER NOT NULL, observed_at TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS prefetch_proposals (
                proposal_id TEXT PRIMARY KEY, principal_id TEXT NOT NULL, capability_id TEXT NOT NULL,
                event_key TEXT NOT NULL, evidence_count INTEGER NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, payload_json TEXT NOT NULL)""")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def observe(self, *, principal_id: str, event_key: str, capability_id: str, hour_local: int) -> dict[str, Any] | None:
        if not principal_id.strip() or len(principal_id) > 128:
            raise ValueError("principal_id must contain 1..128 characters")
        if not event_key.strip() or len(event_key) > 100 or not capability_id.strip() or len(capability_id) > 128:
            raise ValueError("event_key and capability_id are required and bounded")
        if not 0 <= hour_local <= 23:
            raise ValueError("hour_local must be in 0..23")
        with self._connect() as db:
            db.execute("INSERT INTO prefetch_observations VALUES (?, ?, ?, ?, ?)",
                       (principal_id, event_key, capability_id, hour_local, datetime.now(UTC).isoformat()))
            row = db.execute("""SELECT COUNT(*) AS n FROM prefetch_observations
                WHERE principal_id=? AND event_key=? AND capability_id=? AND hour_local=?""",
                (principal_id, event_key, capability_id, hour_local)).fetchone()
            count = int(row["n"])
            if count < self.min_observations:
                return None
            existing = db.execute("""SELECT proposal_id FROM prefetch_proposals
                WHERE principal_id=? AND capability_id=? AND event_key=? AND status='pending'
                ORDER BY created_at DESC LIMIT 1""", (principal_id, capability_id, event_key)).fetchone()
            if existing:
                return None
            proposal_id = str(uuid4())
            payload = {
                "principal_id": principal_id, "capability_id": capability_id,
                "event_key": event_key, "hour_local": hour_local,
                "evidence_count": count, "status": "pending_approval",
                "execution": "not_performed",
                "required_boundary": "approved capability invocation through MCPGateway and PermissionEngine",
            }
            db.execute("INSERT INTO prefetch_proposals VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (proposal_id, principal_id, capability_id, event_key, count, "pending",
                        datetime.now(UTC).isoformat(), json.dumps(payload)))
            payload["proposal_id"] = proposal_id
            return payload

    def proposals(self, *, principal_id: str, limit: int = 20) -> list[dict[str, Any]]:
        limit = min(max(int(limit), 1), self.max_proposals)
        with self._connect() as db:
            rows = db.execute("SELECT payload_json FROM prefetch_proposals WHERE principal_id=? ORDER BY created_at DESC LIMIT ?",
                              (principal_id, limit)).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    async def dispatch_approved(self, *, principal_id: str, proposal_id: str, confirmed: bool,
                                gateway_dispatch: Callable[[dict[str, Any]], Awaitable[Any]]) -> Any:
        if not confirmed:
            raise PermissionError("explicit confirmation is required")
        with self._connect() as db:
            row = db.execute("SELECT * FROM prefetch_proposals WHERE proposal_id=? AND principal_id=?",
                             (proposal_id, principal_id)).fetchone()
            if row is None:
                raise KeyError("prefetch proposal not found")
            if row["status"] != "pending":
                raise ValueError("proposal is no longer pending")
            db.execute("UPDATE prefetch_proposals SET status='approved_dispatching' WHERE proposal_id=?",
                       (proposal_id,))
        # The callback contract is intentionally gateway-specific; this planner
        # has no provider registry and cannot call providers directly.
        try:
            result = await gateway_dispatch(json.loads(row["payload_json"]))
        except Exception:
            with self._connect() as db:
                db.execute("UPDATE prefetch_proposals SET status='pending' WHERE proposal_id=?", (proposal_id,))
            raise
        with self._connect() as db:
            db.execute("UPDATE prefetch_proposals SET status='dispatched' WHERE proposal_id=?", (proposal_id,))
        return result
