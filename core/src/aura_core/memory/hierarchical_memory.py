"""Bounded, scope-isolated hierarchical memory primitives.

Episodic records are persisted as data. Recalled content is explicitly marked
untrusted and must never be interpreted as policy, permissions, or executable
instructions by callers.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class EpisodicRecord:
    record_id: str
    principal_id: str
    task_id: str
    content: str
    source: str
    created_at: float
    metadata: dict[str, Any]
    untrusted: bool = True


@dataclass(frozen=True, slots=True)
class SemanticRecord:
    record_id: str
    principal_id: str
    task_id: str
    content: str
    source_ids: tuple[str, ...]
    created_at: float
    untrusted: bool = True


@dataclass(frozen=True, slots=True)
class ContextItem:
    kind: str
    content: str
    source_ref: str | None = None
    created_at: float = 0.0
    untrusted: bool = True


class WorkingContext:
    """In-memory task context with deterministic entry and character budgets."""

    def __init__(self, *, max_items: int = 32, max_chars: int = 12_000) -> None:
        if max_items < 1 or max_chars < 1:
            raise ValueError("working-context limits must be positive")
        self.max_items = max_items
        self.max_chars = max_chars
        self._items: deque[ContextItem] = deque()

    def add(self, item: ContextItem) -> None:
        content = item.content.strip()
        if not content:
            return
        if len(content) > self.max_chars:
            content = content[: self.max_chars]
        self._items.append(
            ContextItem(
                kind=item.kind[:80],
                content=content,
                source_ref=item.source_ref[:200] if item.source_ref else None,
                created_at=item.created_at or time.time(),
                untrusted=True,
            )
        )
        while len(self._items) > self.max_items or self._char_count() > self.max_chars:
            self._items.popleft()

    def snapshot(self) -> tuple[ContextItem, ...]:
        """Return immutable context entries; consumers must treat content as data."""
        return tuple(self._items)

    def clear(self) -> None:
        self._items.clear()

    def _char_count(self) -> int:
        return sum(len(item.content) for item in self._items)


class SQLiteEpisodicMemory:
    """Append-only SQLite episodic store isolated by principal and task."""

    def __init__(self, path: str | Path, *, max_record_chars: int = 20_000) -> None:
        if max_record_chars < 1:
            raise ValueError("max_record_chars must be positive")
        self.path = str(path)
        self.max_record_chars = max_record_chars
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS episodic_records (
                    record_id TEXT PRIMARY KEY,
                    principal_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            db.execute(
                """CREATE INDEX IF NOT EXISTS idx_episodic_scope_time
                   ON episodic_records(principal_id, task_id, created_at DESC)"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS task_checkpoints (
                    principal_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (principal_id, task_id)
                )"""
            )

            db.execute(
                """CREATE TABLE IF NOT EXISTS semantic_records (
                    record_id TEXT PRIMARY KEY,
                    principal_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_ids_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )"""
            )
            db.execute(
                """CREATE INDEX IF NOT EXISTS idx_semantic_scope_time
                   ON semantic_records(principal_id, task_id, created_at DESC)"""
            )

    def consolidation_candidates(self, *, principal_id: str, limit: int = 20) -> list[EpisodicRecord]:
        principal = self._validate_scope(principal_id, "principal_id")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Consolidation scan limit must be 1..20")
        with self._connect() as db:
            rows = db.execute(
                """SELECT record_id, principal_id, task_id, content, source, created_at, metadata_json
                   FROM episodic_records WHERE principal_id = ?
                   ORDER BY created_at DESC, rowid DESC LIMIT ?""",
                (principal, limit),
            ).fetchall()
        return [EpisodicRecord(row[0], row[1], row[2], row[3], row[4], row[5],
                               json.loads(row[6]), True) for row in rows]

    @staticmethod
    def _semantic_id(principal: str, task: str, source_ids: tuple[str, ...]) -> str:
        return hashlib.sha256(json.dumps(
            [principal, task, sorted(source_ids)], ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")).hexdigest()

    def semantic_exists(self, *, principal_id: str, task_id: str, source_ids: tuple[str, ...]) -> bool:
        principal = self._validate_scope(principal_id, "principal_id")
        task = self._validate_scope(task_id, "task_id")
        with self._connect() as db:
            return db.execute(
                "SELECT 1 FROM semantic_records WHERE principal_id=? AND task_id=? AND record_id=?",
                (principal, task, self._semantic_id(principal, task, source_ids)),
            ).fetchone() is not None

    def save_semantic(self, *, principal_id: str, task_id: str, source_ids: tuple[str, ...],
                      content: str) -> bool:
        """Atomically store a derived, untrusted summary if all source rows still exist."""
        principal = self._validate_scope(principal_id, "principal_id")
        task = self._validate_scope(task_id, "task_id")
        if (type(source_ids) is not tuple or not 2 <= len(source_ids) <= 5
                or len(set(source_ids)) != len(source_ids)
                or any(not isinstance(value, str) or not value or len(value) > 200 for value in source_ids)):
            raise ValueError("Bounded distinct source IDs required")
        if not isinstance(content, str) or not content.strip() or len(content) > min(4000, self.max_record_chars):
            raise ValueError("Invalid semantic summary")
        record_id = self._semantic_id(principal, task, source_ids)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute(
                "SELECT COUNT(*) FROM episodic_records WHERE principal_id=? AND task_id=? AND record_id IN ("
                + ",".join("?" for _ in source_ids) + ")",
                (principal, task, *source_ids),
            ).fetchone()[0]
            if count != len(source_ids):
                return False  # Sources were erased or belong to another scope.
            cursor = db.execute(
                "INSERT OR IGNORE INTO semantic_records VALUES (?, ?, ?, ?, ?, ?)",
                (record_id, principal, task, content.strip(), json.dumps(sorted(source_ids)), time.time()),
            )
            return cursor.rowcount == 1

    def recall_semantic(self, *, principal_id: str, task_id: str, limit: int = 5) -> list[SemanticRecord]:
        principal = self._validate_scope(principal_id, "principal_id")
        task = self._validate_scope(task_id, "task_id")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Semantic recall limit must be 1..20")
        with self._connect() as db:
            rows = db.execute(
                """SELECT record_id, principal_id, task_id, content, source_ids_json, created_at
                   FROM semantic_records WHERE principal_id=? AND task_id=?
                   ORDER BY created_at DESC, record_id LIMIT ?""",
                (principal, task, limit),
            ).fetchall()
        return [SemanticRecord(row[0], row[1], row[2], row[3], tuple(json.loads(row[4])), row[5])
                for row in rows]

    def append(
        self,
        *,
        principal_id: str,
        task_id: str,
        content: str,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> EpisodicRecord:
        principal = self._validate_scope(principal_id, "principal_id")
        task = self._validate_scope(task_id, "task_id")
        safe_content = content.strip()
        safe_source = source.strip()
        if not safe_content:
            raise ValueError("content must not be empty")
        if len(safe_content) > self.max_record_chars:
            raise ValueError("episodic record exceeds configured size limit")
        if not safe_source or len(safe_source) > 120:
            raise ValueError("source must contain 1..120 characters")
        # JSON round-trip rejects non-serializable metadata and detaches caller state.
        safe_metadata = json.loads(json.dumps(metadata or {}, allow_nan=False))
        if not isinstance(safe_metadata, dict):
            raise ValueError("metadata must be an object")
        record = EpisodicRecord(
            record_id=str(uuid.uuid4()),
            principal_id=principal,
            task_id=task,
            content=safe_content,
            source=safe_source,
            created_at=time.time(),
            metadata=safe_metadata,
        )
        with self._connect() as db:
            db.execute(
                """INSERT INTO episodic_records
                   (record_id, principal_id, task_id, content, source, created_at, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.record_id, record.principal_id, record.task_id,
                    record.content, record.source, record.created_at,
                    json.dumps(record.metadata, ensure_ascii=False, allow_nan=False),
                ),
            )
        return record

    def recall(
        self, *, principal_id: str, task_id: str, limit: int = 10
    ) -> list[EpisodicRecord]:
        principal = self._validate_scope(principal_id, "principal_id")
        task = self._validate_scope(task_id, "task_id")
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._connect() as db:
            rows = db.execute(
                """SELECT record_id, principal_id, task_id, content, source,
                          created_at, metadata_json
                   FROM episodic_records
                   WHERE principal_id = ? AND task_id = ?
                   ORDER BY created_at DESC, rowid DESC LIMIT ?""",
                (principal, task, min(limit, 100)),
            ).fetchall()
        return [
            EpisodicRecord(
                record_id=row[0], principal_id=row[1], task_id=row[2],
                content=row[3], source=row[4], created_at=row[5],
                metadata=json.loads(row[6]), untrusted=True,
            )
            for row in rows
        ]

    def save_checkpoint(
        self, *, principal_id: str, task_id: str, state: dict[str, Any]
    ) -> None:
        principal = self._validate_scope(principal_id, "principal_id")
        task = self._validate_scope(task_id, "task_id")
        payload = json.dumps(state, ensure_ascii=False, allow_nan=False)
        if len(payload) > self.max_record_chars:
            raise ValueError("checkpoint exceeds configured size limit")
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS task_checkpoints (
                    principal_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (principal_id, task_id)
                )"""
            )
            db.execute(
                """INSERT INTO task_checkpoints(principal_id, task_id, state_json, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(principal_id, task_id) DO UPDATE SET
                     state_json=excluded.state_json, updated_at=excluded.updated_at""",
                (principal, task, payload, time.time()),
            )

    def load_checkpoint(self, *, principal_id: str, task_id: str) -> dict[str, Any] | None:
        principal = self._validate_scope(principal_id, "principal_id")
        task = self._validate_scope(task_id, "task_id")
        with self._connect() as db:
            row = db.execute(
                """SELECT state_json FROM task_checkpoints
                   WHERE principal_id = ? AND task_id = ?""",
                (principal, task),
            ).fetchone()
        if row is None:
            return None
        value = json.loads(row[0])
        if not isinstance(value, dict):
            raise ValueError("checkpoint state must be an object")
        return value

    def forget_task(
        self, *, principal_id: str, task_id: str, confirmed: bool = False
    ) -> tuple[int, int]:
        """Erase one exact principal/task scope, including its checkpoint.

        This is a low-level persistence primitive, not an authorization
        decision. Callers must authenticate the principal and obtain explicit
        user approval before setting confirmed=True. Neither operation
        reads or modifies another principal's scoped records.
        """
        principal = self._validate_scope(principal_id, "principal_id")
        task = self._validate_scope(task_id, "task_id")
        if confirmed is not True:
            raise PermissionError("explicit task erasure confirmation is required")
        with self._connect() as db:
            db.execute(
                "DELETE FROM semantic_records WHERE principal_id = ? AND task_id = ?",
                (principal, task),
            )
            records = db.execute(
                "DELETE FROM episodic_records WHERE principal_id = ? AND task_id = ?",
                (principal, task),
            ).rowcount
            checkpoints = db.execute(
                "DELETE FROM task_checkpoints WHERE principal_id = ? AND task_id = ?",
                (principal, task),
            ).rowcount
        return records, checkpoints

    @staticmethod
    def _validate_scope(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise ValueError(f"{name} must contain 1..200 characters")
        if any(ord(char) < 32 for char in value):
            raise ValueError(f"{name} contains control characters")
        return value.strip()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=5.0)
        db.row_factory = sqlite3.Row
        return db
