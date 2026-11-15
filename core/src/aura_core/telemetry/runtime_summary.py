"""Offline aggregate performance metrics over existing RuntimeProfiler observations.

Metrics are descriptive, not an authorization, quality rating, hardware
attestation, or estimate of real energy/cost.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Sequence

from aura_core.telemetry.runtime_profiler import RuntimeMeasurement

NAME = re.compile(r"[a-z][a-z0-9_.-]{0,79}\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class OperationSummary:
    component: str
    operation: str
    samples: int
    mean_duration_ms: float
    p95_duration_ms: float
    max_duration_ms: float
    total_cpu_ms: float
    max_rss_bytes: int | None
    duration_budget_exceeded: bool | None
    hardware_verified: bool = False
    acceptance_verified: bool = False
    can_execute: bool = False


def summarize_runtime(
    measurements: Sequence[RuntimeMeasurement],
    *,
    duration_budget_ms: float | None = None,
    max_measurements: int = 1000,
) -> tuple[OperationSummary, ...]:
    """Produce bounded per-operation p95 latency and CPU/RSS aggregate summaries."""
    if type(max_measurements) is not int or not 1 <= max_measurements <= 1000:
        raise ValueError("max_measurements must be 1..1000")
    if duration_budget_ms is not None and (
        type(duration_budget_ms) not in (int, float)
        or not math.isfinite(duration_budget_ms)
        or duration_budget_ms <= 0 or duration_budget_ms > 1e9
    ):
        raise ValueError("invalid duration budget")
    if not isinstance(measurements, (list, tuple)) or len(measurements) > max_measurements:
        raise ValueError("bounded measurement list required")
    grouped: dict[tuple[str, str], list[RuntimeMeasurement]] = {}
    for sample in measurements:
        if type(sample) is not RuntimeMeasurement:
            raise ValueError("RuntimeMeasurement required")
        if (
            type(sample.component) is not str or not NAME.fullmatch(sample.component)
            or type(sample.operation) is not str or not NAME.fullmatch(sample.operation)
        ):
            raise ValueError("invalid component/operation identifier")
        for value in (sample.duration_ms, sample.process_cpu_ms):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1e9:
                raise ValueError("non-finite or negative measurement")
        if sample.rss_bytes is not None and (
            type(sample.rss_bytes) is not int or sample.rss_bytes < 0
        ):
            raise ValueError("invalid RSS value")
        key = (sample.component, sample.operation)
        if len(grouped) >= 50 and key not in grouped:
            raise ValueError("too many distinct operations")
        grouped.setdefault(key, []).append(sample)
    output: list[OperationSummary] = []
    for (component, operation), items in sorted(grouped.items()):
        durations = sorted(float(item.duration_ms) for item in items)
        p95 = durations[max(0, math.ceil(.95 * len(durations)) - 1)]
        peak = [item.rss_bytes for item in items if item.rss_bytes is not None]
        output.append(OperationSummary(
            component=component, operation=operation, samples=len(items),
            mean_duration_ms=round(math.fsum(durations) / len(items), 3),
            p95_duration_ms=round(p95, 3),
            max_duration_ms=round(durations[-1], 3),
            total_cpu_ms=round(math.fsum(float(item.process_cpu_ms) for item in items), 3),
            max_rss_bytes=max(peak) if peak else None,
            duration_budget_exceeded=(
                p95 > duration_budget_ms if duration_budget_ms is not None else None
            ),
        ))
    return tuple(output)
