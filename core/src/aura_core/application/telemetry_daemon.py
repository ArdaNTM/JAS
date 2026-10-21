"""Periodic telemetry sampler with edge-triggered kernel pressure events."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from aura_core.application.system_telemetry import SystemTelemetry
from aura_core.kernel.events import KernelEvent

logger = logging.getLogger(__name__)


class ContinuousTelemetryDaemon:
    """Runs periodic sampling without blocking the API event loop.

    Pressure events are emitted only when the alert signature changes, avoiding
    event storms. The callback is optional because a host may attach its Kernel
    after API construction.
    """

    def __init__(
        self,
        telemetry: SystemTelemetry,
        event_bus_resolver: Callable[[], Any | None],
        *,
        interval_seconds: float = 5.0,
    ) -> None:
        if not 1.0 <= interval_seconds <= 3600.0:
            raise ValueError("interval_seconds must be between 1 and 3600")
        self.telemetry = telemetry
        self._event_bus_resolver = event_bus_resolver
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._last_signature: tuple[str, ...] = ()
        self._samples = 0
        self._errors = 0

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="aura-telemetry-daemon")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def status(self) -> dict[str, object]:
        return {
            "running": self._task is not None and not self._task.done(),
            "interval_seconds": self.interval_seconds,
            "samples": self._samples,
            "errors": self._errors,
            "last_alert_codes": list(self._last_signature),
            "latest": self.telemetry.latest(),
        }

    async def _run(self) -> None:
        while True:
            try:
                snapshot = await asyncio.to_thread(self.telemetry.snapshot)
                self._samples += 1
                signature = tuple(sorted(str(item.get("code", "unknown")) for item in snapshot.get("alerts", [])))
                if signature != self._last_signature:
                    if signature:
                        event_bus = self._event_bus_resolver()
                        if event_bus is not None:
                            event_bus.publish(KernelEvent(
                                event_type="SystemResourcePressure",
                                source_component="continuous_telemetry_daemon",
                                correlation_id="system-pressure:" + ",".join(signature),
                                payload={
                                    "alert_codes": list(signature),
                                    "cpu_percent": snapshot.get("cpu_percent"),
                                    "memory_percent": snapshot.get("memory_percent"),
                                    "recommendations": snapshot.get("recommendations", []),
                                    "policy": "advisory_load_shedding",
                                },
                            ))
                    self._last_signature = signature
            except asyncio.CancelledError:
                raise
            except Exception:
                self._errors += 1
                logger.warning("Continuous telemetry sample failed", exc_info=True)
            await asyncio.sleep(self.interval_seconds)
