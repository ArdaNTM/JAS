"""Small, thread-safe timing trace for a single pipeline request."""

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from time import monotonic


@dataclass(frozen=True, slots=True)
class StageTiming:
    """Timing metadata for one completed pipeline stage."""

    name: str
    started_at: str
    duration_ms: float
    outcome: str


class PipelineTrace:
    """Record stage timings without storing prompts, arguments, or results."""

    def __init__(self, request_id: str) -> None:
        if not request_id or not request_id.strip():
            raise ValueError("request_id is required")

        self.request_id = request_id
        self._lock = RLock()
        self._active: dict[str, tuple[float, str]] = {}
        self._completed: list[StageTiming] = []

    def start_stage(self, name: str) -> None:
        """Start timing a named stage."""
        self._validate_name(name)

        with self._lock:
            if name in self._active:
                raise ValueError(f"Stage is already active: {name}")
            if any(item.name == name for item in self._completed):
                raise ValueError(f"Stage is already completed: {name}")

            started_at = datetime.now(UTC).isoformat()
            self._active[name] = (monotonic(), started_at)

    def finish_stage(self, name: str, outcome: str = "success") -> StageTiming:
        """Finish a stage and return its timing record."""
        self._validate_name(name)
        if outcome not in {"success", "failure", "cancelled"}:
            raise ValueError("Unsupported stage outcome")

        with self._lock:
            active = self._active.pop(name, None)
            if active is None:
                raise ValueError(f"Stage is not active: {name}")

            started, started_at = active
            record = StageTiming(
                name=name,
                started_at=started_at,
                duration_ms=round(max(0.0, monotonic() - started) * 1000, 3),
                outcome=outcome,
            )
            self._completed.append(record)
            return record

    def snapshot(self) -> dict[str, object]:
        """Return a detached snapshot containing metadata only."""
        with self._lock:
            return {
                "request_id": self.request_id,
                "completed_stages": [
                    {
                        "name": item.name,
                        "started_at": item.started_at,
                        "duration_ms": item.duration_ms,
                        "outcome": item.outcome,
                    }
                    for item in self._completed
                ],
                "active_stages": sorted(self._active),
                "stage_count": len(self._completed),
            }

    @staticmethod
    def _validate_name(name: str) -> None:
        if not name or not name.strip():
            raise ValueError("stage name is required")
