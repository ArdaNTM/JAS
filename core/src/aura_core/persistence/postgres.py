"""Optional PostgreSQL repository adapter.

The core depends only on :mod:`aura_core.persistence.repository`; this module is
selected by composition and never imported by the deterministic kernel itself.
"""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from aura_core.persistence.repository import PersistedRecord


class Base(DeclarativeBase):
    pass


class RecordRow(Base):
    __tablename__ = "aura_records"
    entity_type: Mapped[str] = mapped_column(String(128), primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    data: Mapped[dict[str, object]] = mapped_column(JSONB)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)


class PostgresRepository:
    """Async SQLAlchemy implementation with atomic revision increments."""

    def __init__(self, dsn: str) -> None:
        if not dsn:
            raise ValueError("PostgreSQL DSN is required")
        self._engine = create_async_engine(dsn, pool_pre_ping=True)
        self._sessions = async_sessionmaker(self._engine, expire_on_commit=False)

    async def initialize(self) -> None:
        async with self._engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self._engine.dispose()

    async def save(self, record: PersistedRecord) -> PersistedRecord:
        async with self._sessions() as session, session.begin():
            row = await session.get(RecordRow, (record.entity_type, record.entity_id), with_for_update=True)
            revision = 1 if row is None else row.revision + 1
            if row is None:
                session.add(RecordRow(entity_type=record.entity_type, entity_id=record.entity_id, data=dict(record.data), revision=revision))
            else:
                row.data, row.revision = dict(record.data), revision
        return PersistedRecord(record.entity_type, record.entity_id, dict(record.data), revision)

    async def get(self, entity_type: str, entity_id: str) -> PersistedRecord | None:
        async with self._sessions() as session:
            row = await session.get(RecordRow, (entity_type, entity_id))
            if row is None:
                return None
            return PersistedRecord(row.entity_type, row.entity_id, dict(row.data), row.revision)
