"""Immutable in-process audit trail and deterministic telemetry counters."""

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock

from aura_core.kernel.events import KernelEvent


@dataclass(frozen=True, slots=True)
class AuditEntry:
    sequence: int
    event_type: str
    source: str
    payload: dict[str, object]
    timestamp: datetime


class AuditTrail:
    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []
        self._lock = RLock()

    def record_event(self, event: KernelEvent) -> AuditEntry:
        with self._lock:
            entry = AuditEntry(len(self._entries) + 1, event.event_type, event.source_component, dict(event.payload), datetime.now(UTC))
            self._entries.append(entry)
            return entry

    def entries(self) -> tuple[AuditEntry, ...]:
        with self._lock:
            return tuple(self._entries)


class Telemetry:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._lock = RLock()

    def increment(self, metric: str) -> int:
        with self._lock:
            self._counts[metric] = self._counts.get(metric, 0) + 1
            return self._counts[metric]

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(sorted(self._counts.items()))
