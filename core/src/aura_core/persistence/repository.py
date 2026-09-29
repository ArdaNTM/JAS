"""Repository contract separates Core from PostgreSQL drivers."""

from dataclasses import dataclass
from typing import Any, Protocol


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
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], PersistedRecord] = {}

    async def save(self, record: PersistedRecord) -> PersistedRecord:
        key = record.entity_type, record.entity_id
        previous = self._records.get(key)
        saved = PersistedRecord(record.entity_type, record.entity_id, dict(record.data), 1 if previous is None else previous.revision + 1)
        self._records[key] = saved
        return saved

    async def get(self, entity_type: str, entity_id: str) -> PersistedRecord | None:
        return self._records.get((entity_type, entity_id))
