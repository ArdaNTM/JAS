"""Deterministic memory stores; Qdrant is an optional production adapter."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from contextlib import asynccontextmanager
from typing import AsyncIterator, Protocol

import httpx


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    record_id: str
    namespace: str
    content: str
    source: str
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not all((self.record_id, self.namespace, self.content, self.source)):
            raise ValueError("Memory record fields are required")
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class MemoryQuery:
    namespace: str
    text: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    limit: int = 10

    def __post_init__(self) -> None:
        if not self.namespace or self.limit < 1:
            raise ValueError("Memory namespace and positive limit are required")


class MemoryStore(Protocol):
    async def put(self, record: MemoryRecord) -> None:
        raise NotImplementedError

    async def search(self, query: MemoryQuery) -> tuple[MemoryRecord, ...]:
        raise NotImplementedError


class InMemoryStore:
    def __init__(self) -> None:
        self._records: dict[str, MemoryRecord] = {}

    async def put(self, record: MemoryRecord) -> None:
        if record.record_id in self._records:
            raise ValueError(f"Memory record already exists: {record.record_id}")
        self._records[record.record_id] = record

    async def search(self, query: MemoryQuery) -> tuple[MemoryRecord, ...]:
        needle = query.text.casefold()
        matches = [record for record in self._records.values() if record.namespace == query.namespace and needle in record.content.casefold() and all(record.metadata.get(key) == value for key, value in query.metadata.items())]
        return tuple(sorted(matches, key=lambda record: (record.created_at, record.record_id), reverse=True)[:query.limit])


class QdrantStore:
    """HTTP adapter for Qdrant's points API; it requires a reachable server."""

    def __init__(self, base_url: str, collection: str, client: httpx.AsyncClient | None = None) -> None:
        if not base_url or not collection:
            raise ValueError("Qdrant base_url and collection are required")
        self._base_url, self._collection, self._client = base_url.rstrip("/"), collection, client

    async def put(self, record: MemoryRecord) -> None:
        async with self._request_client() as client:
            response = await client.put(f"{self._base_url}/collections/{self._collection}/points", json={"points": [{"id": record.record_id, "vector": [0.0], "payload": {"namespace": record.namespace, "content": record.content, "source": record.source, "metadata": record.metadata, "created_at": record.created_at.isoformat()}}]})
            response.raise_for_status()

    async def search(self, query: MemoryQuery) -> tuple[MemoryRecord, ...]:
        async with self._request_client() as client:
            response = await client.post(f"{self._base_url}/collections/{self._collection}/points/scroll", json={"filter": {"must": [{"key": "namespace", "match": {"value": query.namespace}}]}, "limit": query.limit, "with_payload": True})
            response.raise_for_status()
        points = response.json().get("result", {}).get("points", [])
        return tuple(MemoryRecord(str(point["id"]), point["payload"]["namespace"], point["payload"]["content"], point["payload"]["source"], point["payload"].get("metadata", {}), datetime.fromisoformat(point["payload"]["created_at"])) for point in points if query.text.casefold() in point["payload"]["content"].casefold())

    @asynccontextmanager
    async def _request_client(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._client is not None:
            yield self._client
            return
        async with httpx.AsyncClient(timeout=10.0) as client:
            yield client
