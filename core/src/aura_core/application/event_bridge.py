from __future__ import annotations

import asyncio
from typing import Callable

from aura_core.application.live_events import LiveEventBroker
from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.application.proactive_store import ProactiveSuggestionStore
from aura_core.application.jarvis_intelligence import InitiativeEngine, SelfAdaptationEngine


class EventBusLiveBridge:
    """
    Bridges Kernel EventBus events to the read-only UI event stream.

    This component has no provider access and cannot alter authorization.
    """

    def __init__(
        self,
        event_bus: EventBus,
        broker: LiveEventBroker,
        interval_seconds: float = 0.05,
        suggestion_store: ProactiveSuggestionStore | None = None,
        initiative_engine: InitiativeEngine | None = None,
        adaptation_engine: SelfAdaptationEngine | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")

        self._event_bus = event_bus
        self._broker = broker
        self._interval = interval_seconds
        self._suggestion_store = suggestion_store
        self._initiative_engine = initiative_engine
        self._adaptation_engine = adaptation_engine
        self._unsubscribe: Callable[[], None] | None = None
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return

        self._running = True
        self._unsubscribe = self._event_bus.subscribe(
            "*",
            self._handle,
        )
        self._task = asyncio.create_task(
            self._dispatch_loop(),
            name="aura-eventbus-live-bridge",
        )

    async def stop(self) -> None:
        self._running = False

        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

        if self._task is not None:
            self._task.cancel()

            try:
                await self._task
            except asyncio.CancelledError:
                pass

            self._task = None

    async def _dispatch_loop(self) -> None:
        while self._running:
            dispatched = await self._event_bus.dispatch_once()

            if not dispatched:
                await asyncio.sleep(self._interval)

    async def _handle(self, event: KernelEvent) -> None:
        self._broker.publish(event)
        if self._suggestion_store is not None:
            self._suggestion_store.observe(event)