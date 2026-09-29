"""Thread-safe deterministic fixed-window request limiting."""

from dataclasses import dataclass
from time import monotonic
from threading import RLock


@dataclass(frozen=True, slots=True)
class LimitDecision:
    allowed: bool
    remaining: int


class ExecutionLimiter:
    def __init__(self, maximum: int, window_seconds: float) -> None:
        if maximum < 1 or window_seconds <= 0:
            raise ValueError("Execution limits must be positive")
        self._maximum, self._window = maximum, window_seconds
        self._buckets: dict[str, tuple[float, int]] = {}
        self._lock = RLock()

    def acquire(self, principal_id: str) -> LimitDecision:
        if not principal_id:
            raise ValueError("principal_id is required")
        now = monotonic()
        with self._lock:
            started, count = self._buckets.get(principal_id, (now, 0))
            if now - started >= self._window:
                started, count = now, 0
            if count >= self._maximum:
                self._buckets[principal_id] = started, count
                return LimitDecision(False, 0)
            count += 1
            self._buckets[principal_id] = started, count
            return LimitDecision(True, self._maximum - count)
