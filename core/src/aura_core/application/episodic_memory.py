"""Durable, scoped episodic memory for AURA.

Memory stores user-provided or task-derived records as data, never as executable
instructions. Retrieval is bounded and scoped by principal_id. No provider or
tool is called from this module.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


_ALLOWED_KINDS = {"preference", "fact", "episode", "goal", "lesson"}


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: str
    principal_id: str
    kind: str
    content: str
    tags: tuple[str, ...]
    source_task_id: str | None
    importance: int
    created_at: str
    last_accessed_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "principal_id": self.principal_id,
            "kind": self.kind,
            "content": self.content,
            "tags": list(self.tags),
            "source_task_id": self.source_task_id,
            "importance": self.importance,
            "created_at": self.created_at,
            "last_accessed_at": self.last_accessed_at,
        }


class EpisodicMemoryStore:
    """SQLite-backed memory with principal isolation and explicit deletion."""

    def __init__(self, database_path: str | Path) -> None:
        self._path = Path(database_path).expanduser()
        if str(self._path) != ":memory:":
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @classmethod
    def from_environment(cls) -> "EpisodicMemoryStore":
        configured = os.getenv("AURA_MEMORY_DB")
        if configured:
            path = configured
        else:
            data_dir = Path(os.getenv("AURA_DATA_DIR", Path.home() / ".aura"))
            path = data_dir / "episodic-memory.sqlite3"
        return cls(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self._path), timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS episodic_memory (
                    memory_id TEXT PRIMARY KEY,
                    principal_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    source_task_id TEXT,
                    importance INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    last_accessed_at TEXT NOT NULL
                )
                """
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_scope_time "
                "ON episodic_memory(principal_id, created_at DESC)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_scope_kind "
                "ON episodic_memory(principal_id, kind)"
            )

    @staticmethod
    def _record(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            memory_id=row["memory_id"],
            principal_id=row["principal_id"],
            kind=row["kind"],
            content=row["content"],
            tags=tuple(json.loads(row["tags_json"])),
            source_task_id=row["source_task_id"],
            importance=row["importance"],
            created_at=row["created_at"],
            last_accessed_at=row["last_accessed_at"],
        )

    def remember(
        self,
        *,
        principal_id: str,
        kind: str,
        content: str,
        tags: tuple[str, ...] | list[str] = (),
        source_task_id: str | None = None,
        importance: int = 3,
    ) -> MemoryRecord:
        if not principal_id.strip():
            raise ValueError("principal_id is required")
        if kind not in _ALLOWED_KINDS:
            raise ValueError("Unsupported memory kind")
        content = content.strip()
        if not content or len(content) > 8000:
            raise ValueError("content must contain 1..8000 characters")
        if not 1 <= importance <= 5:
            raise ValueError("importance must be between 1 and 5")
        clean_tags = tuple(sorted({str(tag).strip()[:64] for tag in tags if str(tag).strip()}))
        if len(clean_tags) > 32:
            raise ValueError("At most 32 tags are allowed")
        now = datetime.now(UTC).isoformat()
        memory_id = str(uuid4())
        with self._connect() as db:
            db.execute(
                """INSERT INTO episodic_memory
                   (memory_id, principal_id, kind, content, tags_json,
                    source_task_id, importance, created_at, last_accessed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    memory_id, principal_id, kind, content,
                    json.dumps(clean_tags, ensure_ascii=False),
                    source_task_id, importance, now, now,
                ),
            )
            row = db.execute(
                "SELECT * FROM episodic_memory WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()
        return self._record(row)

    def recall(
        self,
        *,
        principal_id: str,
        query: str = "",
        kind: str | None = None,
        limit: int = 20,
    ) -> list[MemoryRecord]:
        if not principal_id.strip():
            raise ValueError("principal_id is required")
        if kind is not None and kind not in _ALLOWED_KINDS:
            raise ValueError("Unsupported memory kind")
        limit = max(1, min(int(limit), 100))
        clauses = ["principal_id = ?"]
        params: list[object] = [principal_id]
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        # Plain-text retrieval is intentionally bounded; memory text is data,
        # not an instruction source. FTS/embedding search can be added later.
        if query.strip():
            clauses.append("instr(lower(content), lower(?)) > 0")
            params.append(query.strip()[:200])
        params.append(limit)
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM episodic_memory WHERE "
                + " AND ".join(clauses)
                + " ORDER BY importance DESC, created_at DESC LIMIT ?",
                params,
            ).fetchall()
            ids = [row["memory_id"] for row in rows]
            if ids:
                now = datetime.now(UTC).isoformat()
                db.executemany(
                    "UPDATE episodic_memory SET last_accessed_at = ? "
                    "WHERE memory_id = ? AND principal_id = ?",
                    [(now, memory_id, principal_id) for memory_id in ids],
                )
        return [self._record(row) for row in rows]

    def forget(self, *, principal_id: str, memory_id: str) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                "DELETE FROM episodic_memory WHERE memory_id = ? AND principal_id = ?",
                (memory_id, principal_id),
            )
            return cursor.rowcount > 0

    def count(self, *, principal_id: str) -> int:
        with self._connect() as db:
            row = db.execute(
                "SELECT COUNT(*) AS total FROM episodic_memory WHERE principal_id = ?",
                (principal_id,),
            ).fetchone()
        return int(row["total"])
