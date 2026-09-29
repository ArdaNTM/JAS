from dataclasses import dataclass

import pytest

from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.kernel.services import (
    ServiceDefinition,
    ServiceRegistry,
    ServiceCategory,
)
from aura_core.mcp.provider import (
    ProviderDefinition,
    ProviderRegistry,
    ProviderState,
)


@dataclass
class DummyProvider:
    name: str = "dummy"


def create_registry() -> tuple[ServiceRegistry, ProviderRegistry, EventBus]:
    event_bus = EventBus()
    service_registry = ServiceRegistry(event_bus)

    service = service_registry.register(
        ServiceDefinition(
            name="dummy-provider",
            version="0.1.0",
            provider="test",
            category=ServiceCategory.MCP,
        ),
        DummyProvider(),
    )

    provider_registry = ProviderRegistry(
        service_registry,
        event_bus=event_bus,
    )

    provider_registry.register(
        ProviderDefinition(
            provider_id="test:dummy-provider",
            name="dummy-provider",
            version="0.1.0",
            service_id=service.service_id,
        ),
        DummyProvider(),
    )

    return service_registry, provider_registry, event_bus


def test_provider_registration() -> None:
    _, registry, _ = create_registry()

    record = registry.get("test:dummy-provider")

    assert record.definition.name == "dummy-provider"
    assert record.state is ProviderState.REGISTERED
    assert record.available is True
    assert record.healthy is True


def test_provider_resolve() -> None:
    _, registry, _ = create_registry()

    instance = registry.resolve("test:dummy-provider")

    assert isinstance(instance, DummyProvider)


def test_provider_state_update() -> None:
    _, registry, _ = create_registry()

    record = registry.update_state(
        "test:dummy-provider",
        ProviderState.RUNNING,
    )

    assert record.state is ProviderState.RUNNING
    assert registry.get("test:dummy-provider").state is ProviderState.RUNNING


def test_unhealthy_provider_cannot_resolve() -> None:
    _, registry, _ = create_registry()

    registry.update_health(
        "test:dummy-provider",
        available=False,
        healthy=False,
    )

    with pytest.raises(LookupError):
        registry.resolve("test:dummy-provider")


def test_provider_requires_registered_service() -> None:
    event_bus = EventBus()
    service_registry = ServiceRegistry(event_bus)
    registry = ProviderRegistry(service_registry)

    with pytest.raises(KeyError):
        registry.register(
            ProviderDefinition(
                provider_id="test:missing",
                name="missing",
                version="0.1.0",
                service_id="test:missing:0.1.0",
            ),
            DummyProvider(),
        )


def test_duplicate_provider_is_rejected() -> None:
    _, registry, _ = create_registry()

    with pytest.raises(ValueError):
        registry.register(
            ProviderDefinition(
                provider_id="test:dummy-provider",
                name="duplicate",
                version="0.1.0",
                service_id="test:dummy-provider:0.1.0",
            ),
            DummyProvider(),
        )


def test_unregister_retires_provider() -> None:
    _, registry, _ = create_registry()

    record = registry.unregister("test:dummy-provider")

    assert record.state is ProviderState.RETIRED
    assert record.available is False
    assert record.healthy is False

    with pytest.raises(KeyError):
        registry.get("test:dummy-provider")


def dispatch_until_received(
    event_bus: EventBus,
    received: list[KernelEvent],
    *,
    expected_provider_id: str,
) -> None:
    import asyncio

    for _ in range(20):
        asyncio.run(event_bus.dispatch_once())

        if any(
            event.payload.get("provider_id") == expected_provider_id
            for event in received
        ):
            return

    raise AssertionError(
        f"Expected event was not dispatched: {expected_provider_id}"
    )
def test_provider_registration_publishes_event() -> None:
    _, registry, event_bus = create_registry()

    received: list[KernelEvent] = []

    event_bus.subscribe(
        "ProviderRegistered",
        lambda event: received.append(event),
    )

    # Registration already happened in create_registry(), so register
    # another provider to test the event publication.
    service_registry = registry._service_registry

    service = service_registry.register(
        ServiceDefinition(
            name="second-provider",
            version="0.1.0",
            provider="test",
            category=ServiceCategory.MCP,
        ),
        DummyProvider(),
    )

    registry.register(
        ProviderDefinition(
            provider_id="test:second-provider",
            name="second-provider",
            version="0.1.0",
            service_id=service.service_id,
        ),
        DummyProvider(),
    )

    assert event_bus.snapshot()["published_total"] >= 2

    import asyncio

    dispatch_until_received(event_bus, received, expected_provider_id="test:second-provider")

    assert len(received) == 2
    assert received[-1].event_type == "ProviderRegistered"
    assert received[0].source_component == "provider_registry"
    assert received[-1].payload["provider_id"] == "test:second-provider"


def test_provider_state_update_publishes_event() -> None:
    _, registry, event_bus = create_registry()

    received: list[KernelEvent] = []

    event_bus.subscribe(
        "ProviderStateChanged",
        lambda event: received.append(event),
    )

    registry.update_state(
        "test:dummy-provider",
        ProviderState.RUNNING,
    )

    import asyncio

    dispatch_until_received(event_bus, received, expected_provider_id="test:dummy-provider")

    assert len(received) == 1
    assert received[0].event_type == "ProviderStateChanged"
    assert received[0].payload["provider_id"] == "test:dummy-provider"
    assert received[0].payload["state"] is ProviderState.RUNNING


def test_unavailable_provider_publishes_event() -> None:
    _, registry, event_bus = create_registry()

    received: list[KernelEvent] = []

    event_bus.subscribe(
        "ProviderUnavailable",
        lambda event: received.append(event),
    )

    registry.update_health(
        "test:dummy-provider",
        available=False,
        healthy=False,
    )

    import asyncio

    dispatch_until_received(event_bus, received, expected_provider_id="test:dummy-provider")

    assert len(received) == 1
    assert received[0].event_type == "ProviderUnavailable"
    assert received[0].payload["provider_id"] == "test:dummy-provider"
    assert received[0].payload["available"] is False
    assert received[0].payload["healthy"] is False


def test_provider_unregister_publishes_event() -> None:
    _, registry, event_bus = create_registry()

    received: list[KernelEvent] = []

    event_bus.subscribe(
        "ProviderRemoved",
        lambda event: received.append(event),
    )

    registry.unregister("test:dummy-provider")

    import asyncio

    dispatch_until_received(event_bus, received, expected_provider_id="test:dummy-provider")

    assert len(received) == 1
    assert received[0].event_type == "ProviderRemoved"
    assert received[0].payload["provider_id"] == "test:dummy-provider"
    assert received[0].payload["state"] is ProviderState.RETIRED
    assert received[0].payload["available"] is False
    assert received[0].payload["healthy"] is False
