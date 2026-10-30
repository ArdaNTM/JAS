"""Lifecycle-managed dispatcher and quiet-period signals for the Kernel EventBus.

This runtime transports Kernel events only. A quiet period is an application-level
EventBus quiescence signal, not an operating-system idle detector and not authority
to execute tools.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable

from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.telemetry.runtime_profiler import RuntimeProfiler, RuntimeMeasurement

logger = logging.getLogger(__name__)


class EventBusRuntime:
    """Run one bounded polling dispatcher and emit coalesced KernelIdle signals."""

    def __init__(
        self,
        event_bus: EventBus,
        *,
        enabled: bool = True,
        idle_seconds: float = 300.0,
        poll_interval_seconds: float = 0.1,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if idle_seconds < 1:
            raise ValueError("idle_seconds must be at least one second")
        if not 0.01 <= poll_interval_seconds <= 5.0:
            raise ValueError("poll_interval_seconds must be between 0.01 and 5 seconds")
        self.event_bus = event_bus
        self.enabled = bool(enabled)
        self.idle_seconds = float(idle_seconds)
        self.poll_interval_seconds = float(poll_interval_seconds)
        self._monotonic = monotonic
        self._task: asyncio.Task[None] | None = None
        self._stopping = False
        self._last_delivery_at = self._monotonic()
        self._idle_signal_emitted = False
        self._dispatch_errors = 0
        self._dispatched = 0
        self._last_measurement: dict[str, object] | None = None
        self._profiler = RuntimeProfiler(publisher=self._record_measurement)

    def _record_measurement(self, measurement: RuntimeMeasurement) -> None:
        self._last_measurement = measurement.to_dict()

    def start(self) -> None:
        """Start at most one dispatcher task on the current running event loop."""
        if not self.enabled or (self._task is not None and not self._task.done()):
            return
        self._stopping = False
        self._last_delivery_at = self._monotonic()
        self._idle_signal_emitted = False
        self._task = asyncio.create_task(self._run(), name="aura-event-bus-dispatcher")

    async def stop(self, *, timeout_seconds: float = 5.0) -> None:
        """Cancel and await the dispatcher, preserving cancellation semantics."""
        task, self._task = self._task, None
        self._stopping = True
        if task is None:
            return
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=max(0.1, timeout_seconds))
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            logger.error("EventBus dispatcher did not stop within its shutdown budget")
        except Exception:
            logger.exception("EventBus dispatcher failed during shutdown")

    def status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "running": self._task is not None and not self._task.done(),
            "dispatched": self._dispatched,
            "dispatch_errors": self._dispatch_errors,
            "idle_seconds": self.idle_seconds,
            "poll_interval_seconds": self.poll_interval_seconds,
            "mode": "event_bus_quiet_period",
            "tool_execution_performed": False,
            "last_dispatch_measurement": self._last_measurement,
        }

    async def _run(self) -> None:
        while not self._stopping:
            try:
                with self._profiler.measure("event_bus", "dispatch_once"):
                    delivered = await self.event_bus.dispatch_once()
                now = self._monotonic()
                if delivered:
                    self._dispatched += 1
                    self._last_delivery_at = now
                    self._idle_signal_emitted = False
                elif (
                    not self._idle_signal_emitted
                    and now - self._last_delivery_at >= self.idle_seconds
                ):
                    self._idle_signal_emitted = True
                    self.event_bus.publish(
                        KernelEvent(
                            event_type="KernelIdle",
                            source_component="aura.event_bus_runtime",
                            payload={
                                "idle_seconds": self.idle_seconds,
                                "signal_kind": "event_bus_quiet_period",
                            },
                        )
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                self._dispatch_errors += 1
                logger.exception("EventBus dispatch iteration failed")
                # Back off after an unexpected dispatcher-level error so this
                # isolated background task cannot spin or destabilize the app.
                await asyncio.sleep(min(1.0, self.poll_interval_seconds * 5))
            await asyncio.sleep(self.poll_interval_seconds)
