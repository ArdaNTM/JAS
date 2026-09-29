import inspect
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum
from queue import Empty, Queue
from threading import RLock
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Mapping
from uuid import uuid4


class EventPriority(IntEnum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                key: _freeze(item)
                for key, item in value.items()
            }
        )
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class KernelEvent:
    event_type: str
    source_component: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    session_id: str | None = None
    priority: EventPriority = EventPriority.NORMAL
    metadata: Mapping[str, Any] = field(default_factory=dict)
    version: str = "1.0"
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    def __post_init__(self) -> None:
        if not self.event_type:
            raise ValueError("Event type is required")
        if not self.source_component:
            raise ValueError("Event source component is required")
        if not self.version:
            raise ValueError("Event version is required")

        object.__setattr__(self, "payload", _freeze(self.payload))
        object.__setattr__(self, "metadata", _freeze(self.metadata))


EventHandler = Callable[[KernelEvent], Awaitable[None] | None]


@dataclass(frozen=True, slots=True)
class DeadLetter:
    event: KernelEvent
    failure_reason: str
    retry_count: int
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )


@dataclass(frozen=True, slots=True)
class _Delivery:
    event: KernelEvent
    retry_count: int = 0


class EventBus:
    """Thread-safe, in-process event transport for the Kernel foundation."""

    def __init__(self, max_retries: int = 3) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")

        self._max_retries = max_retries
        self._queues = {
            priority: Queue[_Delivery]()
            for priority in EventPriority
        }
        self._subscriptions: dict[str, list[EventHandler]] = defaultdict(list)
        self._dead_letters: list[DeadLetter] = []
        self._published_total = 0
        self._dispatched_total = 0
        self._failed_delivery_total = 0
        self._lock = RLock()

    def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> Callable[[], None]:
        if not event_type:
            raise ValueError("Event type is required")

        with self._lock:
            self._subscriptions[event_type].append(handler)

        def unsubscribe() -> None:
            with self._lock:
                handlers = self._subscriptions.get(event_type, [])
                if handler in handlers:
                    handlers.remove(handler)

        return unsubscribe

    def publish(self, event: KernelEvent) -> None:
        self._queues[event.priority].put_nowait(_Delivery(event=event))
        with self._lock:
            self._published_total += 1

    async def dispatch_once(self) -> bool:
        delivery = self._next_delivery()
        if delivery is None:
            return False

        with self._lock:
            handlers = tuple(
                self._subscriptions.get(delivery.event.event_type, [])
            ) + tuple(self._subscriptions.get("*", []))

        if not handlers:
            self._dead_letter(
                delivery,
                "No subscriber is registered for this event",
            )
            return False

        try:
            for handler in handlers:
                result = handler(delivery.event)
                if inspect.isawaitable(result):
                    await result
        except Exception as exc:
            self._retry_or_dead_letter(delivery, str(exc))
            return False

        with self._lock:
            self._dispatched_total += 1

        return True

    def dead_letters(self) -> tuple[DeadLetter, ...]:
        with self._lock:
            return tuple(self._dead_letters)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "published_total": self._published_total,
                "dispatched_total": self._dispatched_total,
                "failed_delivery_total": self._failed_delivery_total,
                "dead_letter_total": len(self._dead_letters),
                "queued_total": sum(
                    queue.qsize()
                    for queue in self._queues.values()
                ),
            }

    def _next_delivery(self) -> _Delivery | None:
        for priority in EventPriority:
            try:
                return self._queues[priority].get_nowait()
            except Empty:
                continue
        return None

    def _retry_or_dead_letter(
        self,
        delivery: _Delivery,
        failure_reason: str,
    ) -> None:
        with self._lock:
            self._failed_delivery_total += 1

        if delivery.retry_count < self._max_retries:
            self._queues[delivery.event.priority].put_nowait(
                _Delivery(
                    event=delivery.event,
                    retry_count=delivery.retry_count + 1,
                )
            )
            return

        self._dead_letter(delivery, failure_reason)

    def _dead_letter(
        self,
        delivery: _Delivery,
        failure_reason: str,
    ) -> None:
        with self._lock:
            self._dead_letters.append(
                DeadLetter(
                    event=delivery.event,
                    failure_reason=failure_reason,
                    retry_count=delivery.retry_count,
                )
            )
