import asyncio

import pytest

from aura_core.kernel.events import (
    EventBus,
    EventPriority,
    KernelEvent,
)


def make_event(
    event_type: str = "KernelStarted",
    priority: EventPriority = EventPriority.NORMAL,
) -> KernelEvent:
    return KernelEvent(
        event_type=event_type,
        source_component="kernel",
        payload={"nested": {"status": "ready"}},
        correlation_id="correlation-123",
        session_id="session-123",
        priority=priority,
        metadata={"origin": "test"},
    )


def test_event_is_immutable() -> None:
    event = make_event()

    with pytest.raises(TypeError):
        event.payload["new"] = "value"

    with pytest.raises(TypeError):
        event.payload["nested"]["status"] = "changed"


def test_event_bus_dispatches_to_subscriber() -> None:
    bus = EventBus()
    received: list[KernelEvent] = []
    bus.subscribe("KernelStarted", received.append)
    event = make_event()

    bus.publish(event)

    assert asyncio.run(bus.dispatch_once()) is True
    assert received == [event]
    assert bus.snapshot() == {
        "published_total": 1,
        "dispatched_total": 1,
        "failed_delivery_total": 0,
        "dead_letter_total": 0,
        "queued_total": 0,
    }


def test_event_bus_prioritizes_critical_events() -> None:
    bus = EventBus()
    received: list[str] = []
    bus.subscribe("KernelStarted", lambda event: received.append(event.event_id))
    low_priority = make_event(priority=EventPriority.LOW)
    critical_priority = make_event(priority=EventPriority.CRITICAL)

    bus.publish(low_priority)
    bus.publish(critical_priority)

    assert asyncio.run(bus.dispatch_once()) is True
    assert asyncio.run(bus.dispatch_once()) is True
    assert received == [critical_priority.event_id, low_priority.event_id]


def test_event_bus_retries_then_dead_letters_failed_delivery() -> None:
    bus = EventBus(max_retries=1)
    bus.subscribe(
        "KernelStarted",
        lambda event: (_ for _ in ()).throw(RuntimeError("handler failed")),
    )

    bus.publish(make_event())

    assert asyncio.run(bus.dispatch_once()) is False
    assert asyncio.run(bus.dispatch_once()) is False
    dead_letter = bus.dead_letters()[0]
    assert dead_letter.failure_reason == "handler failed"
    assert dead_letter.retry_count == 1
    assert bus.snapshot() == {
        "published_total": 1,
        "dispatched_total": 0,
        "failed_delivery_total": 2,
        "dead_letter_total": 1,
        "queued_total": 0,
    }
