from __future__ import annotations

import hashlib
from typing import Any

from .models import MemoryQuery, MemoryRecord
from .semantic_store import SemanticMemoryStore


class ChatMemory:
    """Scope-isolated persistent chat memory backed by SemanticMemoryStore."""

    NAMESPACE = "chat"

    def __init__(
        self,
        store: SemanticMemoryStore,
        *,
        recall_limit: int = 5,
    ) -> None:
        if recall_limit < 1:
            raise ValueError("recall_limit must be positive")
        self.store = store
        self.recall_limit = recall_limit

    @staticmethod
    def normalize_scope(scope: str | None) -> str | None:
        if not isinstance(scope, str):
            return None
        value = scope.strip()
        if not value or len(value) > 200:
            return None
        if any(ord(char) < 32 for char in value):
            return None
        return value

    @staticmethod
    def _scope_key(scope: str) -> str:
        return hashlib.sha256(scope.encode("utf-8")).hexdigest()

    async def remember(
        self,
        *,
        scope: str | None,
        content: str,
        source: str = "assistant_chat",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        normalized = self.normalize_scope(scope)
        if normalized is None:
            return False
        text = content.strip()
        if not text:
            return False

        safe_metadata = dict(metadata or {})
        safe_metadata["scope_key"] = self._scope_key(normalized)
        record_id = hashlib.sha256(
            (safe_metadata["scope_key"] + "\0" + text).encode("utf-8")
        ).hexdigest()

        await self.store.put(
            MemoryRecord(
                record_id=record_id,
                namespace=self.NAMESPACE,
                content=text,
                source=source,
                metadata=safe_metadata,
            )
        )
        return True

    async def recall(
        self,
        *,
        scope: str | None,
        query: str,
        limit: int | None = None,
    ) -> list[MemoryRecord]:
        normalized = self.normalize_scope(scope)
        if normalized is None or not query.strip():
            return []

        results = await self.store.search(
            MemoryQuery(
                namespace=self.NAMESPACE,
                text=query.strip(),
                metadata={"scope_key": self._scope_key(normalized)},
                limit=min(max(limit or self.recall_limit, 1), 100),
            )
        )
        return [result.record for result in results]