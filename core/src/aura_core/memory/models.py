from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class MemoryRecord:
    record_id: str
    namespace: str
    content: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)


@dataclass(slots=True)
class MemoryQuery:
    namespace: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    limit: int = 10


@dataclass(slots=True)
class Embedding:
    vector: list[float]
    model: str
    dimensions: int


@dataclass(slots=True)
class MemorySearchResult:
    record: MemoryRecord
    score: float
