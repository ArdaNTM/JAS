from __future__ import annotations

from .graph import KnowledgeGraph
from .models import (
    KnowledgeConflict,
    KnowledgeFact,
    KnowledgeRecord,
    KnowledgeSource,
)
from .repository import KnowledgeRepository
from .store import KnowledgeStore


class KnowledgeService:
    def __init__(
        self,
        *,
        store: KnowledgeStore,
        repository: KnowledgeRepository,
        graph: KnowledgeGraph | None = None,
    ) -> None:
        self.store = store
        self.repository = repository
        self.graph = graph or KnowledgeGraph()

    async def initialize(self) -> None:
        await self.repository.initialize()

    async def ingest_source(
        self,
        source: KnowledgeSource,
        payload: bytes,
    ) -> KnowledgeSource:
        source = self.store.put_source(
            source,
            payload,
        )

        await self.repository.save_source(source)

        return source

    async def ingest_record(
        self,
        record: KnowledgeRecord,
    ) -> KnowledgeRecord:
        self.store.put_normalized(record)

        await self.repository.save_record(record)

        return record

    async def ingest_fact(
        self,
        fact: KnowledgeFact,
    ) -> KnowledgeFact:
        self.graph.add_fact(fact)

        await self.repository.save_fact(fact)

        return fact

    async def register_conflict(
        self,
        conflict: KnowledgeConflict,
    ) -> KnowledgeConflict:
        self.graph.add_conflict(conflict)

        await self.repository.save_conflict(conflict)

        return conflict
