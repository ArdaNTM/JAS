"""Async PostgreSQL episodic memory with strict principal scoping."""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from aura_core.application.episodic_memory import MemoryRecord, _ALLOWED_KINDS


class PostgreSQLEpisodicMemoryStore:
    """Remote episodic memory; every query and mutation is principal-scoped."""

    def __init__(self, database_url: str, *, engine: AsyncEngine | None = None) -> None:
        if not isinstance(database_url, str) or not database_url.strip():
            raise ValueError("AURA_DATABASE_URL is required for PostgreSQLEpisodicMemoryStore")
        if not database_url.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise ValueError("AURA_DATABASE_URL must use PostgreSQL")
        self._engine = engine or create_async_engine(database_url, pool_pre_ping=True)
        self._owns_engine = engine is None

    async def initialize(self) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS aura_episodic_memory (
                    memory_id TEXT PRIMARY KEY,
                    principal_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags_json JSONB NOT NULL,
                    source_task_id TEXT,
                    importance INTEGER NOT NULL CHECK(importance BETWEEN 1 AND 5),
                    created_at TIMESTAMPTZ NOT NULL,
                    last_accessed_at TIMESTAMPTZ NOT NULL
                )
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_aura_memory_scope_time
                ON aura_episodic_memory(principal_id, created_at DESC)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_aura_memory_scope_kind
                ON aura_episodic_memory(principal_id, kind)
            """))

    @staticmethod
    def _record(row) -> MemoryRecord:
        tags = row["tags_json"]
        if isinstance(tags, str):
            tags = json.loads(tags)
        return MemoryRecord(
            memory_id=row["memory_id"], principal_id=row["principal_id"], kind=row["kind"],
            content=row["content"], tags=tuple(tags), source_task_id=row["source_task_id"],
            importance=int(row["importance"]), created_at=row["created_at"].isoformat(),
            last_accessed_at=row["last_accessed_at"].isoformat(),
        )

    async def remember(self, *, principal_id: str, kind: str, content: str,
                       tags: tuple[str, ...] | list[str] = (), source_task_id: str | None = None,
                       importance: int = 3) -> MemoryRecord:
        if not isinstance(principal_id, str) or not principal_id.strip():
            raise ValueError("principal_id is required")
        if kind not in _ALLOWED_KINDS:
            raise ValueError("Unsupported memory kind")
        content = content.strip()
        if not content or len(content) > 8000:
            raise ValueError("content must contain 1..8000 characters")
        if type(importance) is not int or not 1 <= importance <= 5:
            raise ValueError("importance must be between 1 and 5")
        clean_tags = tuple(sorted({str(tag).strip()[:64] for tag in tags if str(tag).strip()}))
        if len(clean_tags) > 32:
            raise ValueError("At most 32 tags are allowed")
        now, memory_id = datetime.now(timezone.utc), str(uuid4())
        async with self._engine.begin() as conn:
            result = await conn.execute(text("""
                INSERT INTO aura_episodic_memory
                  (memory_id,principal_id,kind,content,tags_json,source_task_id,importance,created_at,last_accessed_at)
                VALUES (:id,:principal,:kind,:content,CAST(:tags AS JSONB),:task,:importance,:now,:now)
                RETURNING *
            """), {"id":memory_id,"principal":principal_id,"kind":kind,"content":content,
                   "tags":json.dumps(clean_tags,ensure_ascii=False),"task":source_task_id,
                   "importance":importance,"now":now})
            return self._record(result.mappings().one())

    async def recall(self, *, principal_id: str, query: str = "", kind: str | None = None,
                     limit: int = 20) -> list[MemoryRecord]:
        if not isinstance(principal_id, str) or not principal_id.strip():
            raise ValueError("principal_id is required")
        if kind is not None and kind not in _ALLOWED_KINDS:
            raise ValueError("Unsupported memory kind")
        limit = max(1,min(int(limit),100))
        clauses = ["principal_id=:principal"]
        params = {"principal":principal_id,"limit":limit}
        if kind:
            clauses.append("kind=:kind"); params["kind"]=kind
        if query.strip():
            clauses.append("strpos(lower(content),lower(:query))>0"); params["query"]=query.strip()[:200]
        async with self._engine.begin() as conn:
            result = await conn.execute(text("""
                SELECT * FROM aura_episodic_memory WHERE """+" AND ".join(clauses)+"""
                ORDER BY importance DESC, created_at DESC LIMIT :limit
            """),params)
            rows = result.mappings().all()
            if rows:
                ids=[row["memory_id"] for row in rows]
                await conn.execute(text("""
                    UPDATE aura_episodic_memory SET last_accessed_at=:now
                    WHERE principal_id=:principal AND memory_id = ANY(:ids)
                """),{"now":datetime.now(timezone.utc),"principal":principal_id,"ids":ids})
            return [self._record(row) for row in rows]

    @staticmethod
    def _tokens(value: str) -> set[str]:
        normalized=unicodedata.normalize("NFKC",value).casefold()
        return set(re.findall(r"[\wğüşöçıİĞÜŞÖÇ]{2,}",normalized,flags=re.UNICODE))

    async def recall_related(self, *, principal_id: str, query: str,
                             kinds: tuple[str,...] | list[str] | None = None,
                             limit: int = 8) -> list[dict]:
        if not principal_id.strip() or not query.strip() or len(query)>4000:
            raise ValueError("principal_id and a query of 1..4000 characters are required")
        limit=max(1,min(int(limit),50)); tokens=self._tokens(query)
        if not tokens: return []
        async with self._engine.connect() as conn:
            if kinds:
                if any(k not in _ALLOWED_KINDS for k in kinds): raise ValueError("Unsupported memory kind")
                result=await conn.execute(text("""
                    SELECT * FROM aura_episodic_memory WHERE principal_id=:principal
                    AND kind = ANY(:kinds) ORDER BY importance DESC,last_accessed_at DESC LIMIT 500
                """),{"principal":principal_id,"kinds":list(kinds)})
            else:
                result=await conn.execute(text("""
                    SELECT * FROM aura_episodic_memory WHERE principal_id=:principal
                    ORDER BY importance DESC,last_accessed_at DESC LIMIT 500
                """),{"principal":principal_id})
            rows=result.mappings().all()
        ranked=[]
        for row in rows:
            record=self._record(row)
            shared=tokens & self._tokens(record.content+" "+" ".join(record.tags))
            if not shared: continue
            score=(len(shared)/len(tokens)) + record.importance*0.05
            ranked.append((score,record,sorted(shared)))
        ranked.sort(key=lambda item:(item[0],item[1].created_at),reverse=True)
        return [{"memory":record.to_dict(),"score":round(score,4),"matched_terms":terms}
                for score,record,terms in ranked[:limit]]

    async def forget(self, *, principal_id: str, memory_id: str) -> bool:
        if not principal_id.strip() or not memory_id.strip():
            raise ValueError("principal_id and memory_id are required")
        async with self._engine.begin() as conn:
            result=await conn.execute(text("""
                DELETE FROM aura_episodic_memory WHERE principal_id=:principal AND memory_id=:id
            """),{"principal":principal_id,"id":memory_id})
            return result.rowcount == 1

    async def count(self, *, principal_id: str) -> int:
        if not principal_id.strip(): raise ValueError("principal_id is required")
        async with self._engine.connect() as conn:
            result=await conn.execute(text("""
                SELECT count(*) FROM aura_episodic_memory WHERE principal_id=:principal
            """),{"principal":principal_id})
            return int(result.scalar_one())

    async def close(self) -> None:
        if self._owns_engine:
            await self._engine.dispose()
