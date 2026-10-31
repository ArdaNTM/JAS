"""Small in-memory latency histogram for a single local voice runtime."""
from __future__ import annotations

from collections import defaultdict
from math import ceil


class VoiceLatencyMetrics:
    def __init__(self, *, max_samples: int = 512) -> None:
        self._max_samples = max_samples
        self._values: dict[str, list[float]] = defaultdict(list)

    def record(self, stage: str, milliseconds: float) -> None:
        if not stage or milliseconds < 0:
            return
        values = self._values[stage]
        values.append(round(float(milliseconds), 3))
        if len(values) > self._max_samples:
            del values[:len(values) - self._max_samples]

    def snapshot(self) -> dict[str, dict[str, float | int]]:
        result: dict[str, dict[str, float | int]] = {}
        for stage, raw in self._values.items():
            values = sorted(raw)
            if not values:
                continue
            def percentile(q: float) -> float:
                return values[max(0, ceil(q * len(values)) - 1)]
            result[stage] = {"count": len(values), "p50_ms": percentile(.50), "p95_ms": percentile(.95)}
        return result
