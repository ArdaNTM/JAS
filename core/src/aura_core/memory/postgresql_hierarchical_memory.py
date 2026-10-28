"""Principal- and task-scoped PostgreSQL storage for hierarchical episodic memory and checkpoints."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from aura_core.memory.hierarchical_memory import EpisodicRecord, SQLiteEpisodicMemory


class PostgreSQLHierarchicalMemory:
    """Async remote replacement for SQLiteEpisodicMemory."""

    def __init__(self, database_url: str, *, engine: AsyncEngine | None = None,
                 max_record_chars: int = 20_000) -> None:
        if not isinstance(database_url, str) or not database_url.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise ValueError("AURA_DATABASE_URL must use PostgreSQL")
        if not 1 <= max_record_chars <= 100_000:
            raise ValueError("max_record_chars must be between 1 and 100000")
        self._engine = engine or create_async_engine(database_url, pool_pre_ping=True)
        self._owns_engine = engine is None
        self.max_record_chars = max_record_chars

    async def initialize(self) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS aura_hierarchical_episodes (
                    record_id TEXT PRIMARY KEY,
                    principal_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    metadata_json JSONB NOT NULL
                )
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_aura_hierarchical_episodes_scope
                ON aura_hierarchical_episodes(principal_id, task_id, created_at DESC)
            """))
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS aura_task_checkpoints (
                    principal_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    state_json JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY(principal_id, task_id)
                )
            """))

    @staticmethod
    def _scope(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise ValueError(f"{name} must contain 1..256 characters")
        return value.strip()

    async def append(self, *, principal_id: str, task_id: str, content: str,
                     source: str, metadata: dict | None = None) -> EpisodicRecord:
        principal_id = self._scope(principal_id, "principal_id")
        task_id = self._scope(task_id, "task_id")
        if not isinstance(content, str) or not content.strip() or len(content) > self.max_record_chars:
            raise ValueError("content is empty or exceeds configured size limit")
        if not isinstance(source, str) or not source.strip() or len(source) > 120:
            raise ValueError("source must contain 1..120 characters")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")
        record = EpisodicRecord(
            record_id=str(uuid4()), principal_id=principal_id, task_id=task_id,
            content=content.strip(), source=source.strip(),
            created_at=datetime.now(UTC).isoformat(),
            metadata=metadata or {},
        )
        async with self._engine.begin() as conn:
            await conn.execute(text("""
                INSERT INTO aura_hierarchical_episodes
                (record_id, principal_id, task_id, content, source, created_at, metadata_json)
                VALUES (:id,:principal,:task,:content,:source,:created,CAST(:metadata AS JSONB))
            """), {"id":record.record_id,"principal":principal_id,"task":task_id,
                   "content":record.content,"source":record.source,"created":datetime.fromisoformat(record.created_at),
                   "metadata":json.dumps(record.metadata)})
        return record

    async def recall(self, *, principal_id: str, task_id: str, limit: int = 20) -> tuple[EpisodicRecord, ...]:
        principal_id = self._scope(principal_id, "principal_id")
        task_id = self._scope(task_id, "task_id")
        limit = max(1, min(int(limit), 100))
        async with self._engine.connect() as conn:
            result = await conn.execute(text("""
                SELECT record_id, principal_id, task_id, content, source, created_at, metadata_json
                FROM aura_hierarchical_episodes
                WHERE principal_id=:principal AND task_id=:task
                ORDER BY created_at DESC, record_id DESC LIMIT :limit
            """), {"principal":principal_id,"task":task_id,"limit":limit})
            rows = result.mappings().all()
        records = []
        for row in reversed(rows):
            metadata = row["metadata_json"]
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            records.append(EpisodicRecord(
                record_id=row["record_id"],principal_id=row["principal_id"],task_id=row["task_id"],
                content=row["content"],source=row["source"],created_at=row["created_at"].isoformat(),
                metadata=metadata or {},
            ))
        return tuple(records)

    async def save_checkpoint(self, *, principal_id: str, task_id: str, state: dict) -> None:
        principal_id = self._scope(principal_id, "principal_id")
        task_id = self._scope(task_id, "task_id")
        if not isinstance(state, dict):
            raise ValueError("checkpoint state must be an object")
        encoded = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 256_000:
            raise ValueError("checkpoint exceeds configured size limit")
        async with self._engine.begin() as conn:
            await conn.execute(text("""
                INSERT INTO aura_task_checkpoints(principal_id, task_id, state_json, updated_at)
                VALUES (:principal,:task,CAST(:state AS JSONB),:now)
                ON CONFLICT(principal_id,task_id) DO UPDATE
                SET state_json=EXCLUDED.state_json, updated_at=EXCLUDED.updated_at
            """), {"principal":principal_id,"task":task_id,"state":encoded,"now":datetime.now(UTC)})

    async def load_checkpoint(self, *, principal_id: str, task_id: str) -> dict | None:
        principal_id = self._scope(principal_id, "principal_id")
        task_id = self._scope(task_id, "task_id")
        async with self._engine.connect() as conn:
            result = await conn.execute(text("""
                SELECT state_json FROM aura_task_checkpoints
                WHERE principal_id=:principal AND task_id=:task
            """), {"principal":principal_id,"task":task_id})
            value = result.scalar_one_or_none()
        if value is None:
            return None
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict):
            raise ValueError("checkpoint state must be an object")
        return value

    async def close(self) -> None:
        if self._owns_engine:
            await self._engine.dispose()
