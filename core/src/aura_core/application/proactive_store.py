"""Deduplicated, bounded store for reviewable proactive suggestions."""
from __future__ import annotations

from collections import OrderedDict
from threading import RLock

from aura_core.application.proactive_events import ProactiveEventObserver
from aura_core.kernel.events import KernelEvent


class ProactiveSuggestionStore:
    """Project allow-listed Kernel events into a bounded, deduplicated feed."""

    def __init__(self, max_items: int = 100) -> None:
        if max_items < 1:
            raise ValueError("max_items must be positive")
        self._max_items = max_items
        self._observer = ProactiveEventObserver()
        self._items: OrderedDict[str, dict[str, object]] = OrderedDict()
        self._lock = RLock()

    def observe(self, event: KernelEvent) -> dict[str, object] | None:
        suggestion = self._observer.observe(event)
        if suggestion is None:
            return None
        task_id = str(event.payload.get("task_id", ""))
        key = f"{event.event_type}:{event.correlation_id or task_id or event.event_id}"
        with self._lock:
            existing = self._items.get(key)
            if existing is not None:
                return dict(existing)
            item = {
                "id": key,
                **suggestion.to_dict(),
                "timestamp": event.timestamp.isoformat(),
                "task_id": task_id or None,
            }
            self._items[key] = item
            while len(self._items) > self._max_items:
                self._items.popitem(last=False)
            return dict(item)

    def list_items(self, limit: int = 50) -> list[dict[str, object]]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        with self._lock:
            return [dict(item) for item in reversed(tuple(self._items.values()))][:limit]
