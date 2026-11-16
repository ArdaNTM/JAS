"""Explicit PermissionEngine-gated access to the existing scoped episodic store.

This adapter is for trusted Core composition *after principal authentication*.
No provider/MCP tool or permission is registered automatically, and no storage
encryption is claimed. External tool execution must still go through MCPGateway.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from urllib.parse import quote
from uuid import UUID, uuid4

from aura_core.application.episodic_memory import EpisodicMemoryStore, MemoryRecord
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationRequest, PermissionEngine, RiskLevel,
)


class MemoryAccessDenied(PermissionError):
    """A storage operation was not explicitly authorized."""


class MemoryStoreUnavailable(RuntimeError):
    """The existing episodic store could not complete a scoped operation."""


@dataclass(frozen=True, slots=True)
class MemoryEvidence:
    """Remembered text is *untrusted input*, never instructions or policy."""

    memory_id: str
    kind: str
    content: str
    tags: tuple[str, ...]
    source_task_id: str | None
    importance: int
    created_at: str
    trust: str = "UNTRUSTED"


@dataclass(frozen=True, slots=True)
class MemoryWriteReceipt:
    memory_id: str
    created_at: str
    kind: str


def _principal(value: str) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= 128
            or value != value.strip()
            or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
        raise ValueError("authenticated principal must be bounded text")
    return value


def _view(record: MemoryRecord) -> MemoryEvidence:
    return MemoryEvidence(
        memory_id=record.memory_id, kind=record.kind,
        content=record.content, tags=record.tags,
        source_task_id=record.source_task_id,
        importance=record.importance, created_at=record.created_at,
    )


class GovernedEpisodicMemory:
    """No public method accepts a client-supplied principal ID.

    The caller must bind a verified principal when creating this adapter.
    Neither the constructor nor the permission engine is an authentication
    service: deployments must protect the store and composition boundary.
    """

    def __init__(
        self,
        store: EpisodicMemoryStore,
        permission_engine: PermissionEngine,
        *,
        authenticated_principal_id: str,
    ) -> None:
        if not isinstance(store, EpisodicMemoryStore):
            raise TypeError("existing EpisodicMemoryStore required")
        if not isinstance(permission_engine, PermissionEngine):
            raise TypeError("existing Core PermissionEngine required")
        self._store = store
        self._engine = permission_engine
        self._principal_id = _principal(authenticated_principal_id)
        # Distinct exact record namespace; URI-style escaping prevents
        # malicious slashes in the identity from widening a policy scope.
        self._resource_scope = "memory/episodic/" + quote(self._principal_id, safe="")

    def _authorize(self, capability: str, operation: str, risk: RiskLevel) -> None:
        try:
            decision = self._engine.authorize(AuthorizationRequest(
                request_id="memory-access:" + str(uuid4()),
                principal_id=self._principal_id,
                capability_id=capability,
                operation_id=operation,
                resource_scope=self._resource_scope,
                risk_level=risk,
            ))
        except Exception as exc:
            raise MemoryAccessDenied("Memory permission service unavailable") from exc
        # Approval-required and defer are not execution grants. This adapter has
        # no independent approval lifecycle, so both must deny by default.
        if decision.decision is not AuthorizationDecision.ALLOW:
            raise MemoryAccessDenied("Explicit scoped memory permission required")

    def recall(
        self, *, query: str = "", kind: str | None = None, limit: int = 20,
    ) -> tuple[MemoryEvidence, ...]:
        if (not isinstance(query, str) or len(query) > 200
                or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in query)):
            raise ValueError("invalid bounded memory query")
        if kind is not None and (not isinstance(kind, str) or not kind or len(kind) > 64):
            raise ValueError("invalid memory kind")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("memory recall limit must be 1..20")
        self._authorize("memory.episodic.read", "memory.recall", RiskLevel.MEDIUM)
        try:
            records = self._store.recall(
                principal_id=self._principal_id, query=query, kind=kind, limit=limit,
            )
        except (sqlite3.Error, OSError) as exc:
            raise MemoryStoreUnavailable("Scoped memory read failed") from exc
        if any(record.principal_id != self._principal_id for record in records):
            raise MemoryStoreUnavailable("Memory scope integrity check failed")
        return tuple(_view(record) for record in records)

    def remember(
        self,
        *, kind: str, content: str, tags: tuple[str, ...] | list[str] = (),
        source_task_id: str | None = None, importance: int = 3,
    ) -> MemoryWriteReceipt:
        if (not isinstance(content, str) or not 1 <= len(content.strip()) <= 8000
                or any(0xD800 <= ord(c) <= 0xDFFF for c in content)):
            raise ValueError("invalid memory content")
        if not isinstance(kind, str) or not kind or len(kind) > 64:
            raise ValueError("invalid memory kind")
        if not isinstance(tags, (list, tuple)) or len(tags) > 32:
            raise ValueError("invalid memory tags")
        if any(not isinstance(tag, str) or len(tag) > 64 for tag in tags):
            raise ValueError("invalid memory tag")
        if source_task_id is not None and (
            not isinstance(source_task_id, str) or len(source_task_id) > 128
            or any(ord(c) < 32 for c in source_task_id)
        ):
            raise ValueError("invalid source task ID")
        if type(importance) is not int or not 1 <= importance <= 5:
            raise ValueError("invalid memory importance")
        self._authorize("memory.episodic.write", "memory.remember", RiskLevel.HIGH)
        try:
            record = self._store.remember(
                principal_id=self._principal_id, kind=kind, content=content,
                tags=tags, source_task_id=source_task_id, importance=importance,
            )
        except (sqlite3.Error, OSError) as exc:
            raise MemoryStoreUnavailable("Scoped memory write failed") from exc
        if record.principal_id != self._principal_id:
            raise MemoryStoreUnavailable("Memory scope integrity check failed")
        return MemoryWriteReceipt(record.memory_id, record.created_at, record.kind)

    def forget(self, *, memory_id: str) -> bool:
        if not isinstance(memory_id, str) or len(memory_id) > 64:
            raise ValueError("invalid memory ID")
        try:
            canonical = str(UUID(memory_id))
        except (ValueError, AttributeError) as exc:
            raise ValueError("invalid memory ID") from exc
        if memory_id != canonical:
            raise ValueError("memory ID must use canonical UUID format")
        self._authorize("memory.episodic.write", "memory.forget", RiskLevel.HIGH)
        try:
            return self._store.forget(principal_id=self._principal_id, memory_id=canonical)
        except (sqlite3.Error, OSError) as exc:
            raise MemoryStoreUnavailable("Scoped memory deletion failed") from exc
