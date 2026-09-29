from enum import StrEnum

from aura_core.config.kernel import KernelConfig
from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.diagnostics import DiagnosticsService
from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.kernel.health import HealthMonitor, HealthReport
from aura_core.kernel.permissions import PermissionEngine
from aura_core.kernel.services import (
    ServiceCategory,
    ServiceDefinition,
    ServiceRegistry,
    ServiceState,
)
from aura_core.mcp.provider import ProviderRegistry
from aura_core.observability.logging import configure_logging


class KernelState(StrEnum):
    CREATED = "created"
    BOOTSTRAPPING = "bootstrapping"
    INITIALIZING = "initializing"
    REGISTERING = "registering"
    STARTING = "starting"
    READY = "ready"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"


class AuraKernel:
    """Deterministic composition root for the Bootable AURA Kernel."""

    def __init__(self, config: KernelConfig) -> None:
        self.config = config
        self.state = KernelState.CREATED
        self.event_bus: EventBus | None = None
        self.service_registry: ServiceRegistry | None = None
        self.capability_registry: CapabilityRegistry | None = None
        self.provider_registry: ProviderRegistry | None = None
        self.permission_engine: PermissionEngine | None = None
        self.health_monitor: HealthMonitor | None = None
        self.diagnostics: DiagnosticsService | None = None

    def bootstrap(self) -> None:
        self._transition(KernelState.BOOTSTRAPPING)
        configure_logging(self.config.logging.level)

        self._transition(KernelState.INITIALIZING)
        self.event_bus = EventBus()
        self.service_registry = ServiceRegistry(self.event_bus)
        self.capability_registry = CapabilityRegistry(
            self.service_registry,
            event_bus=self.event_bus,
        )
        self.provider_registry = ProviderRegistry(
            self.service_registry,
            event_bus=self.event_bus,
        )
        self.permission_engine = PermissionEngine(
            self.capability_registry,
            event_bus=self.event_bus,
        )
        self.health_monitor = HealthMonitor(
            self.service_registry,
            self.capability_registry,
            event_bus=self.event_bus,
        )
        self.diagnostics = DiagnosticsService(
            self.config,
            self.service_registry,
            self.capability_registry,
            self.health_monitor,
            self.permission_engine,
            self.event_bus,
        )

        self._transition(KernelState.REGISTERING)
        self._register_foundation_services()

        self._transition(KernelState.STARTING)
        self._mark_foundation_services_healthy()
        self._transition(KernelState.READY)
        self.event_bus.publish(
            KernelEvent(
                event_type="KernelReady",
                source_component="kernel",
            )
        )

    def start(self) -> None:
        self._transition(KernelState.RUNNING)
        assert self.event_bus is not None
        self.event_bus.publish(
            KernelEvent(
                event_type="KernelRunning",
                source_component="kernel",
            )
        )

    def stop(self) -> None:
        self._transition(KernelState.STOPPING)
        assert self.service_registry is not None
        for record in reversed(self.service_registry.records()):
            self.service_registry.update_state(
                record.service_id,
                ServiceState.STOPPED,
            )
        self._transition(KernelState.STOPPED)

    def _register_foundation_services(self) -> None:
        assert self.service_registry is not None

        services = (
            ("configuration", self.config, frozenset()),
            (
                "logging",
                configure_logging,
                frozenset({"aura:configuration:0.1.0"}),
            ),
            (
                "event_bus",
                self.event_bus,
                frozenset({"aura:logging:0.1.0"}),
            ),
            ("service_registry", self.service_registry, frozenset()),
            (
                "capability_registry",
                self.capability_registry,
                frozenset({"aura:service_registry:0.1.0"}),
            ),
            (
                "provider_registry",
                self.provider_registry,
                frozenset({"aura:service_registry:0.1.0"}),
            ),
            (
                "permission_engine",
                self.permission_engine,
                frozenset({"aura:capability_registry:0.1.0"}),
            ),
            (
                "health_monitor",
                self.health_monitor,
                frozenset(
                    {
                        "aura:service_registry:0.1.0",
                        "aura:capability_registry:0.1.0",
                        "aura:permission_engine:0.1.0",
                    }
                ),
            ),
            (
                "diagnostics",
                self.diagnostics,
                frozenset({"aura:health_monitor:0.1.0"}),
            ),
        )

        for name, instance, dependencies in services:
            self.service_registry.register(
                ServiceDefinition(
                    name=name,
                    version="0.1.0",
                    provider="aura",
                    category=ServiceCategory.KERNEL,
                    dependencies=dependencies,
                    tags={"foundation"},
                ),
                instance,
            )

    def _mark_foundation_services_healthy(self) -> None:
        assert self.service_registry is not None
        assert self.health_monitor is not None

        for record in self.service_registry.records():
            self.service_registry.update_state(
                record.service_id,
                ServiceState.RUNNING,
            )
            self.health_monitor.report(
                HealthReport(
                    service_id=record.service_id,
                    available=True,
                    ready=True,
                    live=True,
                )
            )

    def _transition(self, target: KernelState) -> None:
        allowed = {
            KernelState.CREATED: {KernelState.BOOTSTRAPPING},
            KernelState.BOOTSTRAPPING: {KernelState.INITIALIZING},
            KernelState.INITIALIZING: {KernelState.REGISTERING},
            KernelState.REGISTERING: {KernelState.STARTING},
            KernelState.STARTING: {KernelState.READY},
            KernelState.READY: {
                KernelState.RUNNING,
                KernelState.STOPPING,
            },
            KernelState.RUNNING: {KernelState.STOPPING},
            KernelState.STOPPING: {KernelState.STOPPED},
            KernelState.STOPPED: set(),
        }

        if target not in allowed[self.state]:
            raise RuntimeError(
                f"Illegal Kernel transition: {self.state} -> {target}"
            )

        self.state = target
