from __future__ import annotations

from dataclasses import dataclass

from aura_core.memory.models import (
    MemoryQuery,
    MemoryRecord,
    MemorySearchResult,
)
from aura_core.memory.semantic_store import (
    SemanticMemoryStore,
)


@dataclass(frozen=True, slots=True)
class EpisodicMemoryEntry:
    record: MemoryRecord
    score: float


class EpisodicMemory:
    """
    Persistent semantic episodic memory.

    Reflections are stored separately from factual knowledge so that
    future learning cycles can retrieve lessons without contaminating
    the canonical knowledge graph.
    """

    NAMESPACE = "episodic"

    def __init__(
        self,
        store: SemanticMemoryStore,
        *,
        recall_limit: int = 5,
    ) -> None:
        if recall_limit < 1:
            raise ValueError(
                "recall_limit must be positive"
            )

        self.store = store
        self.recall_limit = recall_limit

    async def initialize(self) -> None:
        await self.store.initialize()

    async def remember(
        self,
        record: MemoryRecord,
    ) -> None:
        if record.namespace != self.NAMESPACE:
            raise ValueError(
                "Episodic memory requires namespace='episodic'"
            )

        await self.store.put(record)

    async def recall(
        self,
        query: str,
        *,
        limit: int | None = None,
    ) -> list[EpisodicMemoryEntry]:
        results = await self.store.search(
            MemoryQuery(
                namespace=self.NAMESPACE,
                text=query,
                limit=(
                    limit
                    if limit is not None
                    else self.recall_limit
                ),
            )
        )

        return [
            EpisodicMemoryEntry(
                record=result.record,
                score=result.score,
            )
            for result in results
        ]
