from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from threading import RLock

from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.kernel.services import ServiceHealth, ServiceRegistry, ServiceState


class HealthState(StrEnum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    INITIALIZING = "initializing"
    DEGRADED = "degraded"
    RECOVERING = "recovering"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class HealthReport:
    service_id: str
    available: bool
    ready: bool
    live: bool
    latency_ms: float | None = None
    reported_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )


@dataclass(frozen=True, slots=True)
class ComponentHealth:
    service_id: str
    state: HealthState
    report: HealthReport
    failure_count: int
    recovery_count: int


class HealthMonitor:
    """Central health authority for registered Kernel services."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        capability_registry: CapabilityRegistry,
        event_bus: EventBus | None = None,
        degradation_latency_ms: float = 1_000.0,
    ) -> None:
        if degradation_latency_ms <= 0:
            raise ValueError("degradation_latency_ms must be positive")

        self._service_registry = service_registry
        self._capability_registry = capability_registry
        self._event_bus = event_bus
        self._degradation_latency_ms = degradation_latency_ms
        self._components: dict[str, ComponentHealth] = {}
        self._history: dict[str, list[ComponentHealth]] = {}
        self._lock = RLock()

    def report(self, report: HealthReport) -> ComponentHealth:
        record = self._service_registry.get(report.service_id)
        previous = self._components.get(report.service_id)
        state = self._evaluate(report)
        failure_count = (previous.failure_count if previous else 0) + (
            1 if state is HealthState.FAILED else 0
        )
        recovery_count = (previous.recovery_count if previous else 0) + (
            1
            if previous
            and previous.state
            in {HealthState.DEGRADED, HealthState.UNAVAILABLE, HealthState.FAILED}
            and state is HealthState.HEALTHY
            else 0
        )
        component = ComponentHealth(
            service_id=report.service_id,
            state=state,
            report=report,
            failure_count=failure_count,
            recovery_count=recovery_count,
        )

        self._service_registry.update_health(
            report.service_id,
            ServiceHealth(
                available=report.available,
                ready=report.ready,
                live=report.live,
                last_heartbeat=report.reported_at,
                failure_count=failure_count,
            ),
        )
        if state is HealthState.FAILED:
            self._service_registry.update_state(
                report.service_id,
                ServiceState.FAILED,
            )

        for capability in self._capability_registry.providers_for_service(
            report.service_id
        ):
            self._capability_registry.update_health(
                capability.definition.capability_id,
                report.service_id,
                available=report.available and report.ready,
                healthy=state in {HealthState.HEALTHY, HealthState.DEGRADED},
            )

        with self._lock:
            self._components[report.service_id] = component
            self._history.setdefault(report.service_id, []).append(component)

        self._publish_transition(previous, component)
        return component

    def get(self, service_id: str) -> ComponentHealth:
        with self._lock:
            try:
                return self._components[service_id]
            except KeyError as exc:
                raise KeyError(f"No health report for service: {service_id}") from exc

    def history(self, service_id: str) -> tuple[ComponentHealth, ...]:
        with self._lock:
            return tuple(self._history.get(service_id, []))

    def components(self) -> tuple[ComponentHealth, ...]:
        with self._lock:
            return tuple(
                self._components[service_id]
                for service_id in sorted(self._components)
            )

    def _evaluate(self, report: HealthReport) -> HealthState:
        if not report.live:
            return HealthState.FAILED
        if not report.available:
            return HealthState.UNAVAILABLE
        if not report.ready:
            return HealthState.INITIALIZING
        if (
            report.latency_ms is not None
            and report.latency_ms >= self._degradation_latency_ms
        ):
            return HealthState.DEGRADED
        return HealthState.HEALTHY

    def _publish_transition(
        self,
        previous: ComponentHealth | None,
        current: ComponentHealth,
    ) -> None:
        if previous and previous.state is current.state:
            return

        self._publish("HealthChanged", current)
        if current.state is HealthState.HEALTHY:
            event = (
                "ComponentRecovered"
                if previous
                and previous.state
                in {
                    HealthState.DEGRADED,
                    HealthState.UNAVAILABLE,
                    HealthState.FAILED,
                }
                else "ComponentHealthy"
            )
            self._publish(event, current)
        elif current.state is HealthState.DEGRADED:
            self._publish("ComponentDegraded", current)
        elif current.state is HealthState.FAILED:
            self._publish("ComponentFailed", current)

    def _publish(self, event_type: str, component: ComponentHealth) -> None:
        if self._event_bus is None:
            return

        self._event_bus.publish(
            KernelEvent(
                event_type=event_type,
                source_component="health_monitor",
                payload={
                    "service_id": component.service_id,
                    "state": component.state,
                    "failure_count": component.failure_count,
                    "recovery_count": component.recovery_count,
                },
            )
        )
