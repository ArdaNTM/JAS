import asyncio

from aura_core.kernel.capabilities import (
    CapabilityCategory,
    CapabilityDefinition,
    CapabilityRegistry,
    ProviderType,
)
from aura_core.kernel.events import EventBus
from aura_core.kernel.health import HealthMonitor, HealthReport, HealthState
from aura_core.kernel.services import (
    ServiceCategory,
    ServiceDefinition,
    ServiceRegistry,
    ServiceState,
)


def make_monitor(
    event_bus: EventBus | None = None,
) -> tuple[HealthMonitor, ServiceRegistry, CapabilityRegistry, str]:
    services = ServiceRegistry()
    service = services.register(
        ServiceDefinition(
            name="inference",
            version="1.0.0",
            provider="aura",
            category=ServiceCategory.CORE,
        ),
        object(),
    )
    capabilities = CapabilityRegistry(services)
    capabilities.register(
        CapabilityDefinition(
            capability_id="language.inference",
            name="Language Inference",
            version="1.0.0",
            description="Generate responses.",
            provider_id=service.service_id,
            provider_type=ProviderType.SERVICE,
            category=CapabilityCategory.LANGUAGE,
        )
    )
    return (
        HealthMonitor(services, capabilities, event_bus=event_bus),
        services,
        capabilities,
        service.service_id,
    )


def test_monitor_synchronizes_healthy_service_and_capability() -> None:
    monitor, services, capabilities, service_id = make_monitor()

    component = monitor.report(
        HealthReport(
            service_id=service_id,
            available=True,
            ready=True,
            live=True,
            latency_ms=12.0,
        )
    )

    assert component.state is HealthState.HEALTHY
    assert services.get(service_id).health.ready is True
    assert capabilities.resolve("language.inference").healthy is True


def test_monitor_detects_degradation_and_recovery() -> None:
    monitor, _, _, service_id = make_monitor()
    monitor.report(
        HealthReport(service_id=service_id, available=True, ready=True, live=True, latency_ms=2_000.0)
    )

    recovered = monitor.report(
        HealthReport(service_id=service_id, available=True, ready=True, live=True, latency_ms=10.0)
    )

    assert recovered.state is HealthState.HEALTHY
    assert recovered.recovery_count == 1
    assert len(monitor.history(service_id)) == 2


def test_monitor_marks_failed_service_and_provider_unavailable() -> None:
    monitor, services, capabilities, service_id = make_monitor()

    component = monitor.report(
        HealthReport(service_id=service_id, available=False, ready=False, live=False)
    )

    assert component.state is HealthState.FAILED
    assert services.get(service_id).state is ServiceState.FAILED
    assert capabilities.providers("language.inference")[0].available is False


def test_monitor_publishes_health_transitions() -> None:
    event_bus = EventBus()
    events: list[str] = []
    event_bus.subscribe("*", lambda event: events.append(event.event_type))
    monitor, _, _, service_id = make_monitor(event_bus)

    monitor.report(
        HealthReport(service_id=service_id, available=True, ready=True, live=True)
    )

    assert asyncio.run(event_bus.dispatch_once()) is True
    assert asyncio.run(event_bus.dispatch_once()) is True
    assert events == ["HealthChanged", "ComponentHealthy"]
