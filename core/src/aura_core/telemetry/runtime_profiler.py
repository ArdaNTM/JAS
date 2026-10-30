"""Best-effort, non-authoritative runtime profiling."""
from __future__ import annotations
import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable

@dataclass(frozen=True, slots=True)
class RuntimeMeasurement:
    component: str
    operation: str
    duration_ms: float
    process_cpu_ms: float
    rss_bytes: int | None
    energy_joules_estimate: float | None = None
    flops_estimate: int | None = None
    cost_usd_estimate: float | None = None
    estimate_status: str = "not_configured"
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

class RuntimeProfiler:
    """Measure wall/CPU time and RSS; calibrated energy/FLOPs are opt-in."""
    def __init__(self, *, publisher: Callable[[RuntimeMeasurement], None] | None = None,
                 estimator: Callable[[str, str, float], dict[str, float | int]] | None = None):
        self.publisher, self.estimator = publisher, estimator

    @staticmethod
    def _rss() -> int | None:
        try:
            import psutil
            return int(psutil.Process(os.getpid()).memory_info().rss)
        except Exception:
            return None

    def measure(self, component: str, operation: str):
        profiler = self
        class Measurement:
            def __enter__(self):
                self.wall = time.perf_counter()
                self.cpu = time.process_time()
                return self
            def __exit__(self, exc_type, exc, tb):
                elapsed = max(0.0, (time.perf_counter() - self.wall) * 1000)
                cpu = max(0.0, (time.process_time() - self.cpu) * 1000)
                estimates, status = {}, "not_configured"
                if profiler.estimator:
                    try:
                        estimates = profiler.estimator(component, operation, elapsed)
                        status = "estimated"
                    except Exception:
                        status = "estimator_unavailable"
                record = RuntimeMeasurement(component, operation, round(elapsed, 3),
                    round(cpu, 3), profiler._rss(), estimates.get("energy_joules"),
                    estimates.get("flops"), estimates.get("cost_usd"), status)
                if profiler.publisher:
                    try: profiler.publisher(record)
                    except Exception: pass
                return False
        return Measurement()
