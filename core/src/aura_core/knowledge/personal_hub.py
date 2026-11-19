"""Scoped offline personal knowledge view over the existing governed memory.

The caller provides already-authenticated access. This module never opens a
database, reads files, embeds text, invokes a model or grants a capability.
Every search passes through GovernedEpisodicMemory.recall -> PermissionEngine.
"""
from __future__ import annotations

from dataclasses import dataclass

from aura_core.memory.governed_access import GovernedEpisodicMemory, MemoryEvidence


class KnowledgeHubIntegrityError(RuntimeError):
    """Untrusted or inconsistent memory evidence must not become a hub result."""


@dataclass(frozen=True, slots=True)
class KnowledgeHubHit:
    memory_id: str
    kind: str
    preview: str
    tags: tuple[str, ...]
    source_task_id: str | None
    importance: int
    created_at: str
    matched_query_indices: tuple[int, ...]
    content_truncated: bool
    trust: str = "UNTRUSTED"


@dataclass(frozen=True, slots=True)
class KnowledgeHubResult:
    queries: tuple[str, ...]
    hits: tuple[KnowledgeHubHit, ...]
    unique_match_count: int
    truncated: bool
    status: str = "SCOPED_EVIDENCE_ONLY"


class PersonalKnowledgeHub:
    """An opt-in bounded projection, not an independent memory authority."""

    def __init__(self, access: GovernedEpisodicMemory) -> None:
        if not isinstance(access, GovernedEpisodicMemory):
            raise TypeError("GovernedEpisodicMemory required")
        self._access = access

    def search(
        self,
        queries: list[str] | tuple[str, ...],
        *,
        limit: int = 12,
        max_chars: int = 16_000,
    ) -> KnowledgeHubResult:
        if not isinstance(queries, (list, tuple)) or not 1 <= len(queries) <= 4:
            raise ValueError("provide 1..4 explicit knowledge queries")
        checked: list[str] = []
        for query in queries:
            if (not isinstance(query, str) or not 1 <= len(query) <= 200
                    or query != query.strip()
                    or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in query)):
                raise ValueError("invalid bounded knowledge query")
            checked.append(query)
        if len({q.casefold() for q in checked}) != len(checked):
            raise ValueError("duplicate knowledge queries")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("knowledge result limit must be 1..20")
        if type(max_chars) is not int or not 1 <= max_chars <= 32_000:
            raise ValueError("total preview budget must be 1..32000")

        # Query all stages under the existing exact-scope Core permission check.
        # No partial view is emitted on a denied later query.
        evidence_by_id: dict[str, MemoryEvidence] = {}
        positions: dict[str, list[int]] = {}
        for index, query in enumerate(checked):
            records = self._access.recall(query=query, limit=20)
            if not isinstance(records, tuple) or len(records) > 20:
                raise KnowledgeHubIntegrityError("invalid bounded memory response")
            for record in records:
                if not isinstance(record, MemoryEvidence) or record.trust != "UNTRUSTED":
                    raise KnowledgeHubIntegrityError("memory trust contract is invalid")
                if (not isinstance(record.memory_id, str)
                        or not isinstance(record.content, str)
                        or len(record.content) > 8000):
                    raise KnowledgeHubIntegrityError("memory metadata is invalid")
                previous = evidence_by_id.get(record.memory_id)
                if previous is not None and previous != record:
                    raise KnowledgeHubIntegrityError("same record changed during scoped search")
                if previous is None:
                    evidence_by_id[record.memory_id] = record
                    positions[record.memory_id] = []
                positions[record.memory_id].append(index)

        remaining = max_chars
        hits: list[KnowledgeHubHit] = []
        truncated = False
        for record_id, evidence in evidence_by_id.items():
            if len(hits) >= limit or remaining == 0:
                truncated = True
                break
            preview = evidence.content[:remaining]
            was_trimmed = len(preview) != len(evidence.content)
            if was_trimmed:
                truncated = True
            remaining -= len(preview)
            hits.append(KnowledgeHubHit(
                memory_id=record_id, kind=evidence.kind, preview=preview,
                tags=evidence.tags, source_task_id=evidence.source_task_id,
                importance=evidence.importance, created_at=evidence.created_at,
                matched_query_indices=tuple(positions[record_id]),
                content_truncated=was_trimmed,
            ))
        return KnowledgeHubResult(
            queries=tuple(checked), hits=tuple(hits),
            unique_match_count=len(evidence_by_id), truncated=truncated,
        )
