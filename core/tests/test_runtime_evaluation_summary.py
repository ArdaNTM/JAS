"""Descriptive runtime evaluation: no raw provider data or action authority."""
from __future__ import annotations

import math

import pytest

from aura_core.telemetry.runtime_profiler import RuntimeMeasurement, RuntimeProfiler
from aura_core.telemetry.runtime_summary import summarize_runtime


def sample(ms, *, component="mcp_gateway", operation="invoke", rss=100):
    return RuntimeMeasurement(
        component=component, operation=operation, duration_ms=ms,
        process_cpu_ms=ms / 2, rss_bytes=rss,
    )


def test_p95_and_budget_are_descriptive_not_actionable():
    samples = [sample(10), sample(20), sample(100)]
    output = summarize_runtime(samples, duration_budget_ms=50)
    assert len(output) == 1
    summary = output[0]
    assert summary.samples == 3
    assert summary.p95_duration_ms == 100
    assert summary.mean_duration_ms == pytest.approx(43.333, abs=.001)
    assert summary.total_cpu_ms == pytest.approx(65.0)
    assert summary.max_rss_bytes == 100
    assert summary.duration_budget_exceeded is True
    assert summary.hardware_verified is False
    assert summary.acceptance_verified is False
    assert summary.can_execute is False


def test_group_isolation_and_order_independence():
    observations = [
        sample(5, operation="read"),
        sample(3, operation="write"),
        sample(15, operation="read"),
    ]
    assert summarize_runtime(observations) == summarize_runtime(list(reversed(observations)))
    assert [item.operation for item in summarize_runtime(observations)] == ["read", "write"]


def test_existing_profiler_publishes_real_measurement_for_summary():
    observed = []
    profiler = RuntimeProfiler(publisher=observed.append)
    with profiler.measure("mcp_gateway", "invoke"):
        assert 1 + 1 == 2
    assert len(observed) == 1
    summary = summarize_runtime(observed)
    assert summary[0].samples == 1
    assert summary[0].mean_duration_ms >= 0.0
    assert summary[0].hardware_verified is False


@pytest.mark.parametrize("observations", [
    [sample(float("nan"))],
    [sample(float("inf"))],
    [sample(-1)],
    [sample(5, component="../secrets")],
    [RuntimeMeasurement("mcp_gateway", "invoke", 1, 2, -1)],
    [RuntimeMeasurement("mcp_gateway", "invoke", True, 2, 100)],
    [object()],
    [sample(1)] * 1001,
    [sample(1, operation=f"op{i}") for i in range(51)],
])
def test_invalid_data_fails_closed(observations):
    with pytest.raises(ValueError):
        summarize_runtime(observations)


@pytest.mark.parametrize("options", [
    {"duration_budget_ms": True}, {"duration_budget_ms": float("nan")},
    {"duration_budget_ms": math.inf}, {"duration_budget_ms": -1},
    {"max_measurements": False}, {"max_measurements": 1001},
])
def test_invalid_budgets_fail_closed(options):
    with pytest.raises(ValueError):
        summarize_runtime([sample(1)], **options)
