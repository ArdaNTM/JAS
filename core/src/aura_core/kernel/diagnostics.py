from dataclasses import dataclass
from datetime import UTC, datetime

from aura_core.config.kernel import KernelConfig
from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.kernel.health import HealthMonitor, HealthState
from aura_core.kernel.permissions import (
    AuthorizationDecision,
    PermissionEngine,
)
from aura_core.kernel.services import ServiceRegistry


@dataclass(frozen=True, slots=True)
class DiagnosticSnapshot:
    generated_at: datetime
    configuration: dict[str, str | float]
    services: tuple[dict[str, str], ...]
    capabilities: tuple[dict[str, str | bool], ...]
    health: tuple[dict[str, str | int], ...]
    authorization: dict[str, int]
    events: dict[str, int]
    warnings: tuple[str, ...]


class DiagnosticsService:
    """Read-only Kernel inspection and verification service."""

    def __init__(
        self,
        config: KernelConfig,
        service_registry: ServiceRegistry,
        capability_registry: CapabilityRegistry,
        health_monitor: HealthMonitor,
        permission_engine: PermissionEngine,
        event_bus: EventBus,
    ) -> None:
        self._config = config
        self._service_registry = service_registry
        self._capability_registry = capability_registry
        self._health_monitor = health_monitor
        self._permission_engine = permission_engine
        self._event_bus = event_bus

    def snapshot(self) -> DiagnosticSnapshot:
        services = tuple(
            {
                "service_id": record.service_id,
                "category": record.definition.category,
                "state": record.state,
            }
            for record in self._service_registry.records()
        )
        capabilities = tuple(
            {
                "capability_id": record.definition.capability_id,
                "provider_id": record.definition.provider_id,
                "available": record.available,
                "healthy": record.healthy,
                "state": record.state,
            }
            for record in self._capability_registry.records()
        )
        health = tuple(
            {
                "service_id": component.service_id,
                "state": component.state,
                "failure_count": component.failure_count,
                "recovery_count": component.recovery_count,
            }
            for component in self._health_monitor.components()
        )
        audit_records = self._permission_engine.audit_records()
        authorization = {
            "decisions_total": len(audit_records),
            "allow_total": sum(
                record.decision.decision is AuthorizationDecision.ALLOW
                for record in audit_records
            ),
            "deny_total": sum(
                record.decision.decision is AuthorizationDecision.DENY
                for record in audit_records
            ),
            "approval_required_total": sum(
                record.decision.decision
                is AuthorizationDecision.REQUIRE_APPROVAL
                for record in audit_records
            ),
        }
        warnings = tuple(
            [
                f"No health report for service: {record.service_id}"
                for record in self._service_registry.records()
                if record.service_id
                not in {
                    component["service_id"]
                    for component in health
                }
            ]
            + [
                f"Service is not healthy: {component['service_id']}"
                for component in health
                if component["state"] is not HealthState.HEALTHY
            ]
        )
        snapshot = DiagnosticSnapshot(
            generated_at=datetime.now(UTC),
            configuration={
                "runtime": self._config.runtime.runtime,
                "model": self._config.runtime.model,
                "backend_endpoint": self._config.backend.endpoint,
                "backend_timeout": self._config.backend.timeout,
                "log_level": self._config.logging.level,
            },
            services=services,
            capabilities=capabilities,
            health=health,
            authorization=authorization,
            events=self._event_bus.snapshot(),
            warnings=warnings,
        )
        self._publish(snapshot)
        return snapshot

    def _publish(self, snapshot: DiagnosticSnapshot) -> None:
        self._event_bus.publish(
            KernelEvent(
                event_type="DiagnosticGenerated",
                source_component="diagnostics",
                payload={
                    "warning_count": len(snapshot.warnings),
                    "service_count": len(snapshot.services),
                    "capability_count": len(snapshot.capabilities),
                },
            )
        )
        if snapshot.warnings:
            self._event_bus.publish(
                KernelEvent(
                    event_type="DiagnosticWarning",
                    source_component="diagnostics",
                    payload={"warning_count": len(snapshot.warnings)},
                )
            )
