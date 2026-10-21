"""Event-driven, bounded orchestration for review-only background reflection.

This component is deliberately not an agent executor. Event payloads are signals,
never instructions. The only work it can schedule is the existing idle reflection
daemon, which produces review-required memory proposals and does not call tools.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Callable

from aura_core.kernel.events import EventBus, KernelEvent


DEFAULT_REFLECTION_EVENTS = frozenset(
    {
        "KernelIdle",
        "TaskSucceeded",
        "TaskFailed",
        "ConversationTurnCompleted",
        "MemoryUpdated",
    }
)


class EventDrivenOrchestrationCoordinator:
    """Wake bounded reflection from an allow-list of Kernel events.

    The coordinator is opt-in, deduplicates recently handled events, permits only
    one reflection cycle at a time, and enforces a cooldown. It never interprets
    event payload text as a task or dispatches a capability/tool.
    """

    def __init__(
        self,
        *,
        event_bus: EventBus,
        reflection_daemon: Any,
        enabled: bool = False,
        event_types: frozenset[str] = DEFAULT_REFLECTION_EVENTS,
        cooldown_seconds: float = 300.0,
        monotonic: Callable[[], float] = time.monotonic,
        max_recent_events: int = 512,
    ) -> None:
        if not event_types or any(not event_type for event_type in event_types):
            raise ValueError("At least one non-empty event type is required")
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must not be negative")
        if max_recent_events < 1:
            raise ValueError("max_recent_events must be positive")

        self._event_bus = event_bus
        self._reflection_daemon = reflection_daemon
        self._enabled = bool(enabled)
        self._event_types = frozenset(event_types)
        self._cooldown_seconds = float(cooldown_seconds)
        self._monotonic = monotonic
        self._recent_event_ids: deque[str] = deque(maxlen=max_recent_events)
        self._recent_event_set: set[str] = set()
        self._last_cycle_at: float | None = None
        self._cycles_started = 0
        self._cycles_skipped = 0
        self._errors = 0
        self._lock = asyncio.Lock()
        self._unsubscribers: list[Callable[[], None]] = []

    def start(self) -> None:
        """Subscribe to the explicit event allow-list; safe to call repeatedly."""
        if not self._enabled or self._unsubscribers:
            return
        self._unsubscribers = [
            self._event_bus.subscribe(event_type, self._on_event)
            for event_type in sorted(self._event_types)
        ]

    def stop(self) -> None:
        """Remove all subscriptions. In-flight work is not forcefully interrupted."""
        unsubscribers, self._unsubscribers = self._unsubscribers, []
        for unsubscribe in unsubscribers:
            unsubscribe()

    def status(self) -> dict[str, object]:
        return {
            "enabled": self._enabled,
            "subscribed": bool(self._unsubscribers),
            "event_types": sorted(self._event_types),
            "cycles_started": self._cycles_started,
            "cycles_skipped": self._cycles_skipped,
            "errors": self._errors,
            "cooldown_seconds": self._cooldown_seconds,
            "mode": "reviewable_reflection_only",
            "tool_execution_performed": False,
        }

    async def _on_event(self, event: KernelEvent) -> None:
        if not self._enabled or event.event_type not in self._event_types:
            return
        if not self._remember_event(event.event_id):
            self._cycles_skipped += 1
            return

        async with self._lock:
            now = self._monotonic()
            if (
                self._last_cycle_at is not None
                and now - self._last_cycle_at < self._cooldown_seconds
            ):
                self._cycles_skipped += 1
                return

            # run_once owns the idle-time check, principal scoping, bounded recall,
            # stable proposal deduplication, and review-only persistence.
            self._last_cycle_at = now
            try:
                await self._reflection_daemon.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                self._errors += 1
                return
            self._cycles_started += 1

    def _remember_event(self, event_id: str) -> bool:
        if not event_id or event_id in self._recent_event_set:
            return False
        if len(self._recent_event_ids) == self._recent_event_ids.maxlen:
            expired = self._recent_event_ids[0]
            self._recent_event_set.discard(expired)
        self._recent_event_ids.append(event_id)
        self._recent_event_set.add(event_id)
        return True
