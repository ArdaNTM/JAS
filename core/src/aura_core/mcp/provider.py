from dataclasses import dataclass, field, replace
from enum import StrEnum
from threading import RLock
from typing import Any

from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.kernel.services import ServiceRegistry


class ProviderState(StrEnum):
    DISCOVERED = "discovered"
    REGISTERED = "registered"
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class ProviderDefinition:
    provider_id: str
    name: str
    version: str
    service_id: str
    description: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "provider_id",
            "name",
            "version",
            "service_id",
        ):
            if not getattr(self, field_name):
                raise ValueError(
                    f"Provider {field_name} is required"
                )

        object.__setattr__(
            self,
            "metadata",
            dict(self.metadata),
        )


@dataclass(frozen=True, slots=True)
class ProviderRecord:
    definition: ProviderDefinition
    state: ProviderState = ProviderState.REGISTERED
    available: bool = True
    healthy: bool = True


class ProviderRegistry:
    """Authoritative registry for AURA capability providers."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        event_bus: EventBus | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._event_bus = event_bus
        self._records: dict[str, ProviderRecord] = {}
        self._instances: dict[str, Any] = {}
        self._lock = RLock()

    def register(
        self,
        definition: ProviderDefinition,
        instance: Any,
    ) -> ProviderRecord:
        with self._lock:
            if definition.provider_id in self._records:
                raise ValueError(
                    f"Provider is already registered: "
                    f"{definition.provider_id}"
                )

            self._service_registry.get(definition.service_id)

            record = ProviderRecord(definition=definition)
            self._records[definition.provider_id] = record
            self._instances[definition.provider_id] = instance

        self._publish("ProviderRegistered", record)
        return record

    def resolve(self, provider_id: str) -> Any:
        with self._lock:
            try:
                record = self._records[provider_id]
            except KeyError as exc:
                raise KeyError(
                    f"Unknown provider: {provider_id}"
                ) from exc

            if (
                not record.available
                or not record.healthy
                or record.state
                not in {
                    ProviderState.REGISTERED,
                    ProviderState.READY,
                    ProviderState.RUNNING,
                }
            ):
                raise LookupError(
                    f"Provider is unavailable: {provider_id}"
                )

            return self._instances[provider_id]

    def get(self, provider_id: str) -> ProviderRecord:
        with self._lock:
            try:
                return self._records[provider_id]
            except KeyError as exc:
                raise KeyError(
                    f"Unknown provider: {provider_id}"
                ) from exc

    def records(self) -> tuple[ProviderRecord, ...]:
        with self._lock:
            return tuple(
                self._records[provider_id]
                for provider_id in sorted(self._records)
            )

    def update_state(
        self,
        provider_id: str,
        state: ProviderState,
    ) -> ProviderRecord:
        with self._lock:
            try:
                record = self._records[provider_id]
            except KeyError as exc:
                raise KeyError(
                    f"Unknown provider: {provider_id}"
                ) from exc

            updated = replace(record, state=state)
            self._records[provider_id] = updated

        self._publish("ProviderStateChanged", updated)
        return updated

    def update_health(
        self,
        provider_id: str,
        *,
        available: bool,
        healthy: bool,
    ) -> ProviderRecord:
        with self._lock:
            try:
                record = self._records[provider_id]
            except KeyError as exc:
                raise KeyError(
                    f"Unknown provider: {provider_id}"
                ) from exc

            updated = replace(
                record,
                available=available,
                healthy=healthy,
            )
            self._records[provider_id] = updated

        if not available or not healthy:
            self._publish("ProviderUnavailable", updated)

        return updated

    def unregister(
        self,
        provider_id: str,
    ) -> ProviderRecord:
        with self._lock:
            try:
                record = self._records.pop(provider_id)
            except KeyError as exc:
                raise KeyError(
                    f"Unknown provider: {provider_id}"
                ) from exc

            self._instances.pop(provider_id, None)

        retired = replace(
            record,
            state=ProviderState.RETIRED,
            available=False,
            healthy=False,
        )

        self._publish("ProviderRemoved", retired)
        return retired

    def _publish(
        self,
        event_type: str,
        record: ProviderRecord,
    ) -> None:
        if self._event_bus is None:
            return

        self._event_bus.publish(
            KernelEvent(
                event_type=event_type,
                source_component="provider_registry",
                payload={
                    "provider_id": record.definition.provider_id,
                    "service_id": record.definition.service_id,
                    "state": record.state,
                    "available": record.available,
                    "healthy": record.healthy,
                },
            )
        )
