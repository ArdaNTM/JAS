from dataclasses import dataclass, field, replace
from enum import StrEnum
from threading import RLock
from typing import Iterable

from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.kernel.services import ServiceRegistry


class CapabilityCategory(StrEnum):
    VOICE = "voice"
    VISION = "vision"
    MEMORY = "memory"
    LANGUAGE = "language"
    PLANNING = "planning"
    REASONING = "reasoning"
    CODING = "coding"
    BROWSER = "browser"
    RESEARCH = "research"
    AUTOMATION = "automation"
    STORAGE = "storage"
    SECURITY = "security"
    DIAGNOSTICS = "diagnostics"
    INFRASTRUCTURE = "infrastructure"


class ProviderType(StrEnum):
    CORE = "core"
    SERVICE = "service"
    PLUGIN = "plugin"
    MCP = "mcp"
    EXTERNAL_ADAPTER = "external_adapter"
    SYSTEM_INTEGRATION = "system_integration"


class LatencyClass(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class QualityClass(StrEnum):
    BASIC = "basic"
    STANDARD = "standard"
    HIGH = "high"


class CapabilityState(StrEnum):
    DISCOVERED = "discovered"
    REGISTERED = "registered"
    VALIDATED = "validated"
    AVAILABLE = "available"
    AUTHORIZED = "authorized"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    RETIRED = "retired"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    capability_id: str
    name: str
    version: str
    description: str
    provider_id: str
    provider_type: ProviderType
    category: CapabilityCategory
    priority: int = 0
    dependencies: frozenset[str] = field(default_factory=frozenset)
    required_permissions: frozenset[str] = field(default_factory=frozenset)
    latency_class: LatencyClass = LatencyClass.MEDIUM
    quality_class: QualityClass = QualityClass.STANDARD

    def __post_init__(self) -> None:
        for field_name in (
            "capability_id",
            "name",
            "version",
            "description",
            "provider_id",
        ):
            if not getattr(self, field_name):
                raise ValueError(f"Capability {field_name} is required")

        object.__setattr__(self, "dependencies", frozenset(self.dependencies))
        object.__setattr__(
            self,
            "required_permissions",
            frozenset(self.required_permissions),
        )

    @property
    def provider_key(self) -> tuple[str, str]:
        return self.capability_id, self.provider_id


@dataclass(frozen=True, slots=True)
class CapabilityRecord:
    definition: CapabilityDefinition
    state: CapabilityState = CapabilityState.AVAILABLE
    available: bool = True
    healthy: bool = True


class CapabilityRegistry:
    """Authoritative catalog of implementation-independent capabilities."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        event_bus: EventBus | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._event_bus = event_bus
        self._records: dict[tuple[str, str], CapabilityRecord] = {}
        self._lock = RLock()

    def register(
        self,
        definition: CapabilityDefinition,
    ) -> CapabilityRecord:
        with self._lock:

            if definition.provider_key in self._records:
                raise ValueError(
                    "Capability provider is already registered: "
                    f"{definition.provider_id}"
                )

            # Sadece CORE ve SERVICE tipleri ServiceRegistry'de doğrulanır.
            # MCP veya diğer provider tipleri bu kontrolü atlar.
            if definition.provider_type in {ProviderType.CORE, ProviderType.SERVICE}:
                self._service_registry.get(definition.provider_id)

            missing_dependencies = [
                dependency
                for dependency in definition.dependencies
                if not self._providers_for(dependency)
            ]
            if missing_dependencies:
                missing = ", ".join(sorted(missing_dependencies))
                raise ValueError(
                    f"Missing capability dependencies: {missing}"
                )

            record = CapabilityRecord(definition=definition)
            self._records[definition.provider_key] = record

        self._publish("CapabilityRegistered", record)
        return record

    def resolve(self, capability_id: str) -> CapabilityRecord:
        with self._lock:
            candidates = [
                record
                for record in self._providers_for(capability_id)
                if record.available
                and record.healthy
                and record.state
                in {CapabilityState.AVAILABLE, CapabilityState.ACTIVE}
            ]

        if not candidates:
            raise LookupError(
                f"No available provider for capability: {capability_id}"
            )

        return min(candidates, key=self._selection_key)

    def providers(
        self,
        capability_id: str,
    ) -> tuple[CapabilityRecord, ...]:
        with self._lock:
            return tuple(
                sorted(
                    self._providers_for(capability_id),
                    key=self._selection_key,
                )
            )

    def providers_for_service(
        self,
        provider_id: str,
    ) -> tuple[CapabilityRecord, ...]:
        with self._lock:
            return tuple(
                record
                for record in self._records.values()
                if record.definition.provider_id == provider_id
            )

    def records(self) -> tuple[CapabilityRecord, ...]:
        with self._lock:
            return tuple(
                self._records[key]
                for key in sorted(self._records)
            )

    def update_health(
        self,
        capability_id: str,
        provider_id: str,
        *,
        available: bool,
        healthy: bool,
    ) -> CapabilityRecord:
        key = capability_id, provider_id
        with self._lock:
            try:
                record = self._records[key]
            except KeyError as exc:
                raise KeyError(
                    "Unknown capability provider: "
                    f"{capability_id}/{provider_id}"
                ) from exc

            updated = replace(
                record,
                available=available,
                healthy=healthy,
            )
            self._records[key] = updated

        if not available or not healthy:
            self._publish("CapabilityUnavailable", updated)
        return updated

    def update_state(
        self,
        capability_id: str,
        provider_id: str,
        state: CapabilityState,
    ) -> CapabilityRecord:
        key = capability_id, provider_id
        with self._lock:
            try:
                record = self._records[key]
            except KeyError as exc:
                raise KeyError(
                    "Unknown capability provider: "
                    f"{capability_id}/{provider_id}"
                ) from exc

            updated = replace(record, state=state)
            self._records[key] = updated
            return updated

    def unregister(
        self,
        capability_id: str,
        provider_id: str,
    ) -> CapabilityRecord:
        key = capability_id, provider_id
        with self._lock:
            try:
                record = self._records.pop(key)
            except KeyError as exc:
                raise KeyError(
                    "Unknown capability provider: "
                    f"{capability_id}/{provider_id}"
                ) from exc

        retired = replace(record, state=CapabilityState.RETIRED)
        self._publish("CapabilityRemoved", retired)
        return retired

    def _providers_for(
        self,
        capability_id: str,
    ) -> tuple[CapabilityRecord, ...]:
        return tuple(
            record
            for (registered_id, _), record in self._records.items()
            if registered_id == capability_id
        )

    @staticmethod
    def _selection_key(record: CapabilityRecord) -> tuple[int, int, int, str]:
        quality_rank = {
            QualityClass.HIGH: 0,
            QualityClass.STANDARD: 1,
            QualityClass.BASIC: 2,
        }
        latency_rank = {
            LatencyClass.LOW: 0,
            LatencyClass.MEDIUM: 1,
            LatencyClass.HIGH: 2,
        }
        definition = record.definition
        return (
            -definition.priority,
            quality_rank[definition.quality_class],
            latency_rank[definition.latency_class],
            definition.provider_id,
        )

    def _publish(self, event_type: str, record: CapabilityRecord) -> None:
        if self._event_bus is None:
            return

        self._event_bus.publish(
            KernelEvent(
                event_type=event_type,
                source_component="capability_registry",
                payload={
                    "capability_id": record.definition.capability_id,
                    "provider_id": record.definition.provider_id,
                    "state": record.state,
                },
            )
        )