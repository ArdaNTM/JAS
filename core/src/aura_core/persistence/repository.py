"""Repository contracts and remote PostgreSQL adapter.

This generic record repository is a building block, not a replacement for the
specialized workflow/approval/memory stores. Remote mode remains gated until
those stores and artifact writes are migrated and composed through it.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


@dataclass(frozen=True, slots=True)
class PersistedRecord:
    entity_type: str
    entity_id: str
    data: dict[str, Any]
    revision: int = 1


class Repository(Protocol):
    async def save(self, record: PersistedRecord) -> PersistedRecord:
        raise NotImplementedError

    async def get(self, entity_type: str, entity_id: str) -> PersistedRecord | None:
        raise NotImplementedError


class InMemoryRepository:
    """Explicitly ephemeral adapter for unit tests and non-durable use."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], PersistedRecord] = {}

    async def save(self, record: PersistedRecord) -> PersistedRecord:
        key = record.entity_type, record.entity_id
        previous = self._records.get(key)
        saved = PersistedRecord(
            record.entity_type, record.entity_id, copy.deepcopy(record.data),
            1 if previous is None else previous.revision + 1,
        )
        self._records[key] = saved
        return saved

    async def get(self, entity_type: str, entity_id: str) -> PersistedRecord | None:
        return self._records.get((entity_type, entity_id))


class PostgreSQLRepository:
    """JSONB-backed remote record store with atomic revision increments.

    Requires a PostgreSQL URL and reachable database. It never falls back to
    SQLite or in-memory persistence. The caller owns engine lifecycle and schema
    migration policy; `initialize` is explicit rather than an implicit write
    during application startup.
    """

    def __init__(self, database_url: str, *, engine: AsyncEngine | None = None) -> None:
        if not isinstance(database_url, str) or not database_url.strip():
            raise ValueError("AURA_DATABASE_URL is required for PostgreSQLRepository")
        if not database_url.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise ValueError("AURA_DATABASE_URL must use PostgreSQL")
        self._engine = engine or create_async_engine(database_url, pool_pre_ping=True)
        self._owns_engine = engine is None

    async def initialize(self) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(text("""
                CREATE TABLE IF NOT EXISTS aura_persisted_records (
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    data JSONB NOT NULL,
                    revision BIGINT NOT NULL CHECK (revision >= 1),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (entity_type, entity_id)
                )
            """))

    async def save(self, record: PersistedRecord) -> PersistedRecord:
        if not record.entity_type.strip() or not record.entity_id.strip():
            raise ValueError("entity_type and entity_id are required")
        if not isinstance(record.data, dict):
            raise ValueError("record.data must be a dictionary")
        payload = json.dumps(record.data, ensure_ascii=False, separators=(",", ":"))
        async with self._engine.begin() as connection:
            result = await connection.execute(text("""
                INSERT INTO aura_persisted_records (entity_type, entity_id, data, revision)
                VALUES (:entity_type, :entity_id, CAST(:data AS JSONB), 1)
                ON CONFLICT (entity_type, entity_id) DO UPDATE
                    SET data = EXCLUDED.data,
                        revision = aura_persisted_records.revision + 1,
                        updated_at = now()
                RETURNING revision
            """), {
                "entity_type": record.entity_type,
                "entity_id": record.entity_id,
                "data": payload,
            })
            revision = int(result.scalar_one())
        return PersistedRecord(record.entity_type, record.entity_id, dict(record.data), revision)

    async def get(self, entity_type: str, entity_id: str) -> PersistedRecord | None:
        async with self._engine.connect() as connection:
            result = await connection.execute(text("""
                SELECT data, revision FROM aura_persisted_records
                WHERE entity_type = :entity_type AND entity_id = :entity_id
            """), {"entity_type": entity_type, "entity_id": entity_id})
            row = result.mappings().one_or_none()
        if row is None:
            return None
        data = row["data"]
        if isinstance(data, str):
            data = json.loads(data)
        return PersistedRecord(entity_type, entity_id, copy.deepcopy(dict(data)), int(row["revision"]))

    async def close(self) -> None:
        if self._owns_engine:
            await self._engine.dispose()
