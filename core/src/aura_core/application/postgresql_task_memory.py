"""Async task-memory coordinator for PostgreSQL-backed hierarchical memory."""
from __future__ import annotations

from dataclasses import asdict

from aura_core.memory.hierarchical_memory import ContextItem, WorkingContext
from aura_core.memory.postgresql_hierarchical_memory import PostgreSQLHierarchicalMemory


class PostgreSQLTaskMemoryCoordinator:
    """Remote counterpart of TaskMemoryCoordinator; recalled content stays untrusted."""

    def __init__(self, store: PostgreSQLHierarchicalMemory, *, max_recalled: int = 8) -> None:
        if not 1 <= max_recalled <= 50:
            raise ValueError("max_recalled must be between 1 and 50")
        self.store = store
        self.max_recalled = max_recalled
        self._contexts: dict[tuple[str, str], WorkingContext] = {}

    async def initialize(self) -> None:
        await self.store.initialize()

    async def begin(self, *, principal_id: str, task_id: str, goal: str) -> tuple[ContextItem, ...]:
        scope = (principal_id, task_id)
        context = WorkingContext(max_items=32, max_chars=12_000)
        checkpoint = await self.store.load_checkpoint(principal_id=principal_id, task_id=task_id)
        if checkpoint and isinstance(checkpoint.get("context"), list):
            for raw in checkpoint["context"][-self.max_recalled:]:
                if isinstance(raw, dict) and isinstance(raw.get("content"), str):
                    context.add(ContextItem(
                        kind=str(raw.get("kind", "recalled"))[:80],
                        content=raw["content"][:12_000],
                        source_ref=str(raw.get("source_ref", ""))[:200] or None,
                        untrusted=True,
                    ))
        for record in reversed(await self.store.recall(
            principal_id=principal_id, task_id=task_id, limit=self.max_recalled
        )):
            context.add(ContextItem(
                kind="episodic", content=record.content, source_ref=record.record_id,
                created_at=record.created_at, untrusted=True,
            ))
        context.add(ContextItem(kind="goal", content=goal[:4000], untrusted=True))
        self._contexts[scope] = context
        await self.store.append(
            principal_id=principal_id, task_id=task_id,
            content=f"Task started: {goal[:4000]}", source="task_lifecycle",
            metadata={"event": "started"},
        )
        await self._save(principal_id, task_id, context, state="running")
        return context.snapshot()

    async def finish(self, *, principal_id: str, task_id: str, state: str, summary: str) -> None:
        if state not in {"succeeded", "failed", "cancelled"}:
            raise ValueError("unsupported task state")
        safe_summary = summary[:4000].strip() or f"Task {state}"
        await self.store.append(
            principal_id=principal_id, task_id=task_id, content=safe_summary,
            source="task_lifecycle", metadata={"event": state},
        )
        context = self._contexts.get((principal_id, task_id), WorkingContext())
        context.add(ContextItem(kind="outcome", content=safe_summary, untrusted=True))
        await self._save(principal_id, task_id, context, state=state)
        self._contexts.pop((principal_id, task_id), None)

    async def _save(self, principal_id: str, task_id: str, context: WorkingContext, *, state: str) -> None:
        await self.store.save_checkpoint(
            principal_id=principal_id, task_id=task_id,
            state={"state": state, "context": [asdict(item) for item in context.snapshot()]},
        )

    async def close(self) -> None:
        await self.store.close()
