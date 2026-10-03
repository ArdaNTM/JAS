"""Bounded WebSocket projection of kernel events.

This is an observer only: it cannot invoke a provider or alter authorization.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import asdict
from datetime import datetime
from typing import Any

from aura_core.kernel.events import KernelEvent


class LiveEventBroker:
    def __init__(self, max_events: int = 256) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._history: list[dict[str, Any]] = []
        self._max_events = max_events

    def publish(self, event: KernelEvent) -> None:
        payload = {
            "id": event.event_id,
            "event": event.event_type,
            "source": event.source_component,
            "timestamp": event.timestamp.isoformat(),
            "correlation_id": event.correlation_id,
            "data": dict(event.payload),
        }
        self._history = (self._history + [payload])[-self._max_events :]
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # A slow client must not apply backpressure to the kernel.
                pass

    async def stream(self):
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        self._subscribers.add(queue)
        try:
            for event in self._history:
                yield event
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)
