import asyncio

import pytest

from aura_core.kernel.capabilities import (
    CapabilityCategory,
    CapabilityDefinition,
    CapabilityRegistry,
    ProviderType,
)
from aura_core.kernel.events import EventBus
from aura_core.kernel.services import (
    ServiceCategory,
    ServiceDefinition,
    ServiceRegistry,
)


CAPABILITY_ID = "language.inference"


def make_service_definition(name: str) -> ServiceDefinition:
    return ServiceDefinition(
        name=name,
        version="1.0.0",
        provider="aura",
        category=ServiceCategory.CORE,
    )


def make_definition(
    provider_id: str,
    priority: int = 0,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id=CAPABILITY_ID,
        name="Language Inference",
        version="1.0.0",
        description="Generate language-model responses.",
        provider_id=provider_id,
        provider_type=ProviderType.SERVICE,
        category=CapabilityCategory.LANGUAGE,
        priority=priority,
        required_permissions={"model.infer"},
    )


def make_registry() -> tuple[ServiceRegistry, CapabilityRegistry]:
    services = ServiceRegistry()
    return services, CapabilityRegistry(services)


def test_registry_resolves_highest_priority_healthy_provider() -> None:
    services, registry = make_registry()
    lower_provider = services.register(
        make_service_definition("mock_inference"), object()
    )
    higher_provider = services.register(
        make_service_definition("ollama_inference"), object()
    )
    lower = registry.register(make_definition(lower_provider.service_id, 10))
    higher = registry.register(make_definition(higher_provider.service_id, 20))

    resolved = registry.resolve(CAPABILITY_ID)

    assert resolved == higher
    assert registry.providers(CAPABILITY_ID) == (higher, lower)
    assert resolved.definition.required_permissions == {"model.infer"}


def test_registry_fails_over_when_preferred_provider_is_unhealthy() -> None:
    services, registry = make_registry()
    lower_provider = services.register(
        make_service_definition("mock_inference"), object()
    )
    higher_provider = services.register(
        make_service_definition("ollama_inference"), object()
    )
    lower = registry.register(make_definition(lower_provider.service_id, 10))
    registry.register(make_definition(higher_provider.service_id, 20))

    registry.update_health(
        CAPABILITY_ID,
        higher_provider.service_id,
        available=False,
        healthy=False,
    )

    assert registry.resolve(CAPABILITY_ID) == lower


def test_registry_rejects_unknown_provider_and_duplicate_provider() -> None:
    _, registry = make_registry()

    with pytest.raises(KeyError, match="Unknown service"):
        registry.register(make_definition("aura:missing:1.0.0"))

    services, registry = make_registry()
    provider = services.register(make_service_definition("inference"), object())
    definition = make_definition(provider.service_id)
    registry.register(definition)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(definition)


def test_registry_publishes_registration_and_unavailability_events() -> None:
    event_bus = EventBus()
    received: list[str] = []
    event_bus.subscribe("*", lambda event: received.append(event.event_type))
    services = ServiceRegistry()
    provider = services.register(make_service_definition("inference"), object())
    registry = CapabilityRegistry(services, event_bus=event_bus)
    registry.register(make_definition(provider.service_id))
    registry.update_health(
        CAPABILITY_ID,
        provider.service_id,
        available=False,
        healthy=False,
    )

    assert asyncio.run(event_bus.dispatch_once()) is True
    assert asyncio.run(event_bus.dispatch_once()) is True
    assert received == ["CapabilityRegistered", "CapabilityUnavailable"]
