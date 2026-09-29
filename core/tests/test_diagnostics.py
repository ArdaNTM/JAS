import asyncio

from aura_core.config.backend import BackendConfig
from aura_core.config.kernel import KernelConfig
from aura_core.config.logging import LoggingConfig
from aura_core.config.runtime import RuntimeConfig
from aura_core.kernel.capabilities import (
    CapabilityCategory,
    CapabilityDefinition,
    CapabilityRegistry,
    ProviderType,
)
from aura_core.kernel.diagnostics import DiagnosticsService
from aura_core.kernel.events import EventBus
from aura_core.kernel.health import HealthMonitor, HealthReport
from aura_core.kernel.permissions import (
    AuthorizationRequest,
    PermissionEngine,
    RiskLevel,
)
from aura_core.kernel.services import (
    ServiceCategory,
    ServiceDefinition,
    ServiceRegistry,
)


def test_diagnostics_collects_read_only_kernel_snapshot() -> None:
    event_bus = EventBus()
    events: list[str] = []
    event_bus.subscribe("*", lambda event: events.append(event.event_type))
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
    health = HealthMonitor(services, capabilities)
    health.report(
        HealthReport(
            service_id=service.service_id,
            available=True,
            ready=True,
            live=True,
        )
    )
    permissions = PermissionEngine(capabilities)
    permissions.authorize(
        AuthorizationRequest(
            request_id="request-123",
            principal_id="agent:test",
            capability_id="language.inference",
            operation_id="model.infer",
            resource_scope="local_model",
            risk_level=RiskLevel.LOW,
        )
    )
    config = KernelConfig(
        runtime=RuntimeConfig(runtime="ollama", model="qwen3:4b-instruct-2507-q4_K_M"),
        backend=BackendConfig(),
        logging=LoggingConfig(),
    )
    diagnostics = DiagnosticsService(
        config,
        services,
        capabilities,
        health,
        permissions,
        event_bus,
    )
    services_before = services.records()
    capabilities_before = capabilities.records()

    snapshot = diagnostics.snapshot()

    assert snapshot.configuration["runtime"] == "ollama"
    assert snapshot.services[0]["service_id"] == service.service_id
    assert snapshot.capabilities[0]["capability_id"] == "language.inference"
    assert snapshot.health[0]["state"] == "healthy"
    assert snapshot.authorization["deny_total"] == 1
    assert snapshot.warnings == ()
    assert services.records() == services_before
    assert capabilities.records() == capabilities_before
    assert asyncio.run(event_bus.dispatch_once()) is True
    assert events == ["DiagnosticGenerated"]


def test_diagnostics_warns_when_service_has_no_health_report() -> None:
    event_bus = EventBus()
    services = ServiceRegistry()
    service = services.register(
        ServiceDefinition(
            name="logging",
            version="1.0.0",
            provider="aura",
            category=ServiceCategory.KERNEL,
        ),
        object(),
    )
    capabilities = CapabilityRegistry(services)
    health = HealthMonitor(services, capabilities)
    permissions = PermissionEngine(capabilities)
    config = KernelConfig(
        runtime=RuntimeConfig(model="mock"),
        backend=BackendConfig(),
        logging=LoggingConfig(),
    )
    diagnostics = DiagnosticsService(
        config,
        services,
        capabilities,
        health,
        permissions,
        event_bus,
    )

    snapshot = diagnostics.snapshot()

    assert snapshot.warnings == (
        f"No health report for service: {service.service_id}",
    )
