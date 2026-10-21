from __future__ import annotations

import asyncio

import pytest

from aura_core.application.event_bus_runtime import EventBusRuntime
from aura_core.kernel.events import EventBus, KernelEvent


def test_runtime_dispatches_events_and_start_is_idempotent() -> None:
    async def scenario() -> None:
        bus = EventBus()
        seen: list[str] = []

        async def handler(item: KernelEvent) -> None:
            seen.append(item.event_id)

        bus.subscribe("TaskSucceeded", handler)
        runtime = EventBusRuntime(
            bus, idle_seconds=60, poll_interval_seconds=0.01
        )
        runtime.start()
        first_task = runtime._task
        runtime.start()
        assert runtime._task is first_task

        bus.publish(
            KernelEvent(event_type="TaskSucceeded", source_component="test")
        )
        for _ in range(100):
            if seen:
                break
            await asyncio.sleep(0.01)

        assert len(seen) == 1
        assert runtime.status()["dispatched"] >= 1
        await runtime.stop()
        assert runtime.status()["running"] is False

    asyncio.run(scenario())


def test_runtime_emits_one_idle_signal_per_quiet_period() -> None:
    async def scenario() -> None:
        bus = EventBus()
        clock = [10.0]
        idle_signals: list[KernelEvent] = []

        async def idle_handler(item: KernelEvent) -> None:
            idle_signals.append(item)

        bus.subscribe("KernelIdle", idle_handler)
        runtime = EventBusRuntime(
            bus,
            idle_seconds=5,
            poll_interval_seconds=0.01,
            monotonic=lambda: clock[0],
        )
        runtime.start()
        clock[0] += 6

        for _ in range(100):
            if idle_signals:
                break
            await asyncio.sleep(0.01)

        assert len(idle_signals) == 1
        assert idle_signals[0].source_component == "aura.event_bus_runtime"
        assert idle_signals[0].payload["signal_kind"] == "event_bus_quiet_period"

        # The idle event itself is activity; a second signal requires a new quiet
        # interval, rather than an unbounded stream of self-generated idle events.
        await asyncio.sleep(0.05)
        assert len(idle_signals) == 1
        await runtime.stop()

    asyncio.run(scenario())


def test_runtime_contains_dispatcher_errors_and_keeps_running() -> None:
    async def scenario() -> None:
        bus = EventBus()
        runtime = EventBusRuntime(
            bus, idle_seconds=60, poll_interval_seconds=0.01
        )
        original = bus.dispatch_once
        calls = 0

        async def flaky_dispatch() -> bool:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("temporary dispatch failure")
            return await original()

        bus.dispatch_once = flaky_dispatch  # type: ignore[method-assign]
        runtime.start()
        for _ in range(100):
            if calls >= 2:
                break
            await asyncio.sleep(0.01)

        assert calls >= 2
        assert runtime.status()["dispatch_errors"] == 1
        assert runtime.status()["running"] is True
        await runtime.stop()

    asyncio.run(scenario())


def test_runtime_can_be_disabled_and_shutdown_is_idempotent() -> None:
    async def scenario() -> None:
        bus = EventBus()
        runtime = EventBusRuntime(bus, enabled=False)
        runtime.start()
        assert runtime.status()["running"] is False
        await runtime.stop()
        await runtime.stop()

    asyncio.run(scenario())


def test_runtime_rejects_unbounded_or_invalid_polling_settings() -> None:
    bus = EventBus()
    with pytest.raises(ValueError):
        EventBusRuntime(bus, idle_seconds=0)
    with pytest.raises(ValueError):
        EventBusRuntime(bus, poll_interval_seconds=0)
