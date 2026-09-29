import asyncio

import pytest

from aura_core.kernel.events import EventBus
from aura_core.kernel.services import (
    ServiceCategory,
    ServiceDefinition,
    ServiceHealth,
    ServiceRegistry,
    ServiceState,
)


def make_definition(
    name: str = "logging",
    dependencies: frozenset[str] = frozenset(),
) -> ServiceDefinition:
    return ServiceDefinition(
        name=name,
        version="1.0.0",
        provider="aura",
        category=ServiceCategory.KERNEL,
        capabilities={"structured_logging"},
        dependencies=dependencies,
        tags={"foundation", "observability"},
        priority=10,
    )


def test_registry_registers_resolves_and_discovers_service() -> None:
    registry = ServiceRegistry()
    instance = object()
    record = registry.register(make_definition(), instance)

    assert record.service_id == "aura:logging:1.0.0"
    assert registry.resolve(record.service_id) is instance
    assert registry.get(record.service_id) == record
    assert registry.find_by_category(ServiceCategory.KERNEL) == (record,)
    assert registry.find_by_capability("structured_logging") == (record,)
    assert registry.find_by_provider("aura") == (record,)
    assert registry.find_by_version("1.0.0") == (record,)
    assert registry.find_by_tags({"foundation"}) == (record,)


def test_registry_rejects_duplicate_and_missing_dependency() -> None:
    registry = ServiceRegistry()
    definition = make_definition()
    registry.register(definition, object())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(definition, object())

    with pytest.raises(ValueError, match="Missing service dependencies"):
        registry.register(
            make_definition(
                name="event_bus",
                dependencies=frozenset({"aura:missing:1.0.0"}),
            ),
            object(),
        )


def test_registry_tracks_health_state_and_removal() -> None:
    registry = ServiceRegistry()
    record = registry.register(make_definition(), object())
    health = ServiceHealth(available=True, ready=True, live=True)

    updated_health = registry.update_health(record.service_id, health)
    stopped = registry.update_state(
        record.service_id,
        ServiceState.STOPPED,
    )

    assert updated_health.health == health
    assert registry.find_by_health(ready=True) == (stopped,)
    assert stopped.state is ServiceState.STOPPED

    removed = registry.unregister(record.service_id)

    assert removed.state is ServiceState.REMOVED
    with pytest.raises(KeyError, match="Unknown service"):
        registry.get(record.service_id)


def test_registry_publishes_lifecycle_events() -> None:
    event_bus = EventBus()
    received: list[str] = []
    event_bus.subscribe("ServiceRegistered", lambda event: received.append(event.event_type))
    registry = ServiceRegistry(event_bus=event_bus)

    registry.register(make_definition(), object())

    assert asyncio.run(event_bus.dispatch_once()) is True
    assert received == ["ServiceRegistered"]
