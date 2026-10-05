from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import NAMESPACE_URL, uuid5


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class KnowledgeEvidence:
    source_id: str
    locator: str
    quote: str | None = None
    confidence: float = 0.5


@dataclass(slots=True)
class KnowledgeSource:
    source_id: str
    uri: str
    source_type: str
    title: str | None = None
    local_path: str | None = None
    checksum_sha256: str | None = None
    discovered_at: datetime = field(default_factory=utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class KnowledgeFact:
    fact_id: str
    subject: str
    predicate: str
    object: str
    confidence: float
    evidence: list[KnowledgeEvidence] = field(default_factory=list)
    status: str = "active"
    first_seen_at: datetime = field(default_factory=utcnow)
    last_seen_at: datetime = field(default_factory=utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class KnowledgeConflict:
    conflict_id: str
    fact_a: str
    fact_b: str
    reason: str
    status: str = "open"
    created_at: datetime = field(default_factory=utcnow)
    resolution: str | None = None


@dataclass(slots=True)
class KnowledgeRecord:
    record_id: str
    namespace: str
    content: str
    source_id: str
    kind: str = "document"
    title: str | None = None
    confidence: float = 0.5
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)
    facts: list[str] = field(default_factory=list)
    evidence: list[KnowledgeEvidence] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        namespace: str,
        content: str,
        source_id: str,
        kind: str = "document",
        title: str | None = None,
        confidence: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> "KnowledgeRecord":
        content_hash = hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()

        record_id = str(
            uuid5(
                NAMESPACE_URL,
                "|".join(
                    (
                        namespace,
                        source_id,
                        kind,
                        content_hash,
                    )
                ),
            )
        )

        return cls(
            record_id=record_id,
            namespace=namespace,
            content=content,
            source_id=source_id,
            kind=kind,
            title=title,
            confidence=max(
                0.0,
                min(1.0, confidence),
            ),
            metadata=dict(metadata or {}),
        )
