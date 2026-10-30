"""Durable, principal-isolated graph-edge stores; no tool execution or inference."""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from threading import RLock
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def _require_text(value: str, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must contain 1..{maximum} characters")
    return value.strip()


def _limit(value: int) -> int:
    if type(value) is not int or value < 1 or value > 50:
        raise ValueError("limit must be between 1 and 50")
    return value


def _depth(value: int) -> int:
    if type(value) is not int or value not in (1, 2):
        raise ValueError("depth must be 1 or 2")
    return value


class SQLiteGraphStore:
    """Local durable adjacency index; each connection is short lived."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS aura_graph_edges(
                fact_id TEXT PRIMARY KEY, principal_id TEXT NOT NULL,
                subject TEXT NOT NULL, predicate TEXT NOT NULL,
                object TEXT NOT NULL)""")
            db.execute("""CREATE INDEX IF NOT EXISTS idx_aura_graph_edges_scope
                ON aura_graph_edges(principal_id, subject, fact_id)""")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    async def initialize(self):
        return None

    def _insert(self, principal_id, subject, predicate, object_value):
        fact_id = str(uuid4())
        with self._lock, self._connect() as db:
            db.execute("""INSERT INTO aura_graph_edges(
                fact_id, principal_id, subject, predicate, object)
                VALUES(?,?,?,?,?)""", (fact_id, principal_id, subject, predicate, object_value))
        return fact_id

    async def insert(self, *, principal_id, subject, predicate, object):
        principal_id = _require_text(principal_id, "principal_id", 256)
        subject = _require_text(subject, "subject", 200)
        predicate = _require_text(predicate, "predicate", 200)
        object = _require_text(object, "object", 2000)
        return await asyncio.to_thread(self._insert, principal_id, subject, predicate, object)

    def _query(self, principal_id, subject, limit, depth):
        result = []
        frontier, seen = [subject], {subject}
        with self._lock, self._connect() as db:
            for _ in range(depth):
                next_frontier = []
                for node in frontier:
                    rows = db.execute("""SELECT fact_id, subject, predicate, object
                        FROM aura_graph_edges WHERE principal_id=? AND subject=?
                        ORDER BY fact_id LIMIT ?""",
                        (principal_id, node, limit - len(result))).fetchall()
                    for fact_id, sub, pred, obj in rows:
                        result.append({"fact_id": fact_id, "subject": sub,
                            "predicate": pred, "object": obj, "untrusted": True})
                        if obj not in seen:
                            seen.add(obj)
                            next_frontier.append(obj)
                        if len(result) >= limit:
                            return result
                frontier = next_frontier
                if not frontier:
                    break
        return result

    async def query(self, *, principal_id, subject, limit=20, depth=1):
        return await asyncio.to_thread(self._query,
            _require_text(principal_id, "principal_id", 256),
            _require_text(subject, "subject", 200), _limit(limit), _depth(depth))

    async def close(self):
        return None


class PostgreSQLGraphStore:
    """Remote GraphRAG adjacency store with scoped SQL and no local fallback."""

    def __init__(self, database_url: str, *, engine: AsyncEngine | None = None):
        if not isinstance(database_url, str) or not database_url.startswith(
                ("postgresql+asyncpg://", "postgresql://")):
            raise ValueError("Graph store requires PostgreSQL")
        self._engine = engine or create_async_engine(database_url, pool_pre_ping=True)
        self._owns_engine = engine is None

    async def initialize(self):
        async with self._engine.begin() as conn:
            await conn.execute(text("""CREATE TABLE IF NOT EXISTS aura_graph_edges(
                fact_id TEXT PRIMARY KEY, principal_id TEXT NOT NULL,
                subject TEXT NOT NULL, predicate TEXT NOT NULL,
                object TEXT NOT NULL)"""))
            await conn.execute(text("""CREATE INDEX IF NOT EXISTS idx_aura_graph_edges_scope
                ON aura_graph_edges(principal_id, subject, fact_id)"""))

    async def insert(self, *, principal_id, subject, predicate, object):
        values = {
            "id": str(uuid4()),
            "principal": _require_text(principal_id, "principal_id", 256),
            "subject": _require_text(subject, "subject", 200),
            "predicate": _require_text(predicate, "predicate", 200),
            "object": _require_text(object, "object", 2000),
        }
        async with self._engine.begin() as conn:
            await conn.execute(text("""INSERT INTO aura_graph_edges(
                fact_id, principal_id, subject, predicate, object)
                VALUES(:id,:principal,:subject,:predicate,:object)"""), values)
        return values["id"]

    async def query(self, *, principal_id, subject, limit=20, depth=1):
        principal = _require_text(principal_id, "principal_id", 256)
        subject = _require_text(subject, "subject", 200)
        limit, depth = _limit(limit), _depth(depth)
        result, frontier, seen = [], [subject], {subject}
        async with self._engine.connect() as conn:
            for _ in range(depth):
                next_frontier = []
                for node in frontier:
                    rows = (await conn.execute(text("""SELECT fact_id, subject, predicate, object
                        FROM aura_graph_edges WHERE principal_id=:principal AND subject=:subject
                        ORDER BY fact_id LIMIT :limit"""),
                        {"principal": principal, "subject": node, "limit": limit - len(result)}
                    )).mappings().all()
                    for row in rows:
                        obj = row["object"]
                        result.append({**dict(row), "untrusted": True})
                        if obj not in seen:
                            seen.add(obj)
                            next_frontier.append(obj)
                        if len(result) >= limit:
                            return result
                frontier = next_frontier
                if not frontier:
                    break
        return result

    async def close(self):
        if self._owns_engine:
            await self._engine.dispose()
