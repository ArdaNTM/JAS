from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from threading import RLock
from typing import Any, Iterable

from aura_core.kernel.events import EventBus, KernelEvent


class ServiceCategory(StrEnum):
    KERNEL = "kernel"
    CORE = "core"
    CAPABILITY = "capability"
    AGENT = "agent"
    PLUGIN = "plugin"
    MCP = "mcp"
    INTEGRATION = "integration"
    INFRASTRUCTURE = "infrastructure"


class ServiceState(StrEnum):
    REGISTERED = "registered"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class ServiceHealth:
    available: bool = False
    ready: bool = False
    live: bool = False
    last_heartbeat: datetime | None = None
    failure_count: int = 0


@dataclass(frozen=True, slots=True)
class ServiceDefinition:
    name: str
    version: str
    provider: str
    category: ServiceCategory
    capabilities: frozenset[str] = field(default_factory=frozenset)
    dependencies: frozenset[str] = field(default_factory=frozenset)
    tags: frozenset[str] = field(default_factory=frozenset)
    priority: int = 0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Service name is required")
        if not self.version:
            raise ValueError("Service version is required")
        if not self.provider:
            raise ValueError("Service provider is required")

        object.__setattr__(self, "capabilities", frozenset(self.capabilities))
        object.__setattr__(self, "dependencies", frozenset(self.dependencies))
        object.__setattr__(self, "tags", frozenset(self.tags))

    @property
    def service_id(self) -> str:
        return f"{self.provider}:{self.name}:{self.version}"


@dataclass(frozen=True, slots=True)
class ServiceRecord:
    definition: ServiceDefinition
    health: ServiceHealth = field(default_factory=ServiceHealth)
    state: ServiceState = ServiceState.REGISTERED
    registered_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    @property
    def service_id(self) -> str:
        return self.definition.service_id


class ServiceRegistry:
    """Authoritative, thread-safe catalog for Kernel runtime services."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._event_bus = event_bus
        self._records: dict[str, ServiceRecord] = {}
        self._instances: dict[str, Any] = {}
        self._lock = RLock()

    def register(
        self,
        definition: ServiceDefinition,
        instance: Any,
    ) -> ServiceRecord:
        with self._lock:
            if definition.service_id in self._records:
                raise ValueError(
                    f"Service is already registered: {definition.service_id}"
                )

            missing_dependencies = (
                definition.dependencies - self._records.keys()
            )
            if missing_dependencies:
                missing = ", ".join(sorted(missing_dependencies))
                raise ValueError(f"Missing service dependencies: {missing}")

            if definition.service_id in definition.dependencies:
                raise ValueError("A service cannot depend on itself")

            record = ServiceRecord(definition=definition)
            self._records[record.service_id] = record
            self._instances[record.service_id] = instance

        self._publish("ServiceRegistered", record)
        return record

    def resolve(self, service_id: str) -> Any:
        with self._lock:
            try:
                return self._instances[service_id]
            except KeyError as exc:
                raise KeyError(f"Unknown service: {service_id}") from exc

    def get(self, service_id: str) -> ServiceRecord:
        with self._lock:
            try:
                return self._records[service_id]
            except KeyError as exc:
                raise KeyError(f"Unknown service: {service_id}") from exc

    def find_by_category(
        self,
        category: ServiceCategory,
    ) -> tuple[ServiceRecord, ...]:
        return self._find(
            lambda record: record.definition.category == category
        )

    def find_by_capability(
        self,
        capability: str,
    ) -> tuple[ServiceRecord, ...]:
        return self._find(
            lambda record: capability in record.definition.capabilities
        )

    def find_by_provider(
        self,
        provider: str,
    ) -> tuple[ServiceRecord, ...]:
        return self._find(
            lambda record: record.definition.provider == provider
        )

    def find_by_version(
        self,
        version: str,
    ) -> tuple[ServiceRecord, ...]:
        return self._find(
            lambda record: record.definition.version == version
        )

    def find_by_tags(
        self,
        tags: Iterable[str],
    ) -> tuple[ServiceRecord, ...]:
        required_tags = frozenset(tags)
        return self._find(
            lambda record: required_tags <= record.definition.tags
        )

    def find_by_health(
        self,
        *,
        available: bool | None = None,
        ready: bool | None = None,
        live: bool | None = None,
    ) -> tuple[ServiceRecord, ...]:
        def matches(record: ServiceRecord) -> bool:
            health = record.health
            return (
                (available is None or health.available == available)
                and (ready is None or health.ready == ready)
                and (live is None or health.live == live)
            )

        return self._find(matches)

    def update_health(
        self,
        service_id: str,
        health: ServiceHealth,
    ) -> ServiceRecord:
        with self._lock:
            record = self.get(service_id)
            updated = replace(record, health=health)
            self._records[service_id] = updated
            return updated

    def update_state(
        self,
        service_id: str,
        state: ServiceState,
    ) -> ServiceRecord:
        with self._lock:
            record = self.get(service_id)
            updated = replace(record, state=state)
            self._records[service_id] = updated

        if state is ServiceState.FAILED:
            self._publish("ServiceFailed", updated)
        return updated

    def unregister(self, service_id: str) -> ServiceRecord:
        with self._lock:
            record = self.get(service_id)
            if record.state not in {
                ServiceState.STOPPED,
                ServiceState.FAILED,
            }:
                raise ValueError(
                    "Service must be stopped or failed before removal"
                )

            removed = replace(record, state=ServiceState.REMOVED)
            del self._records[service_id]
            del self._instances[service_id]

        self._publish("ServiceRemoved", removed)
        return removed

    def records(self) -> tuple[ServiceRecord, ...]:
        with self._lock:
            return tuple(
                self._records[service_id]
                for service_id in sorted(self._records)
            )

    def _find(self, predicate) -> tuple[ServiceRecord, ...]:
        with self._lock:
            return tuple(
                record
                for record in self.records()
                if predicate(record)
            )

    def _publish(self, event_type: str, record: ServiceRecord) -> None:
        if self._event_bus is None:
            return

        self._event_bus.publish(
            KernelEvent(
                event_type=event_type,
                source_component="service_registry",
                payload={
                    "service_id": record.service_id,
                    "name": record.definition.name,
                    "state": record.state,
                },
            )
        )
