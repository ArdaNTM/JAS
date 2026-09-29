from aura_core.observability.metrics import RequestMetrics


def test_metrics_tracks_success_failure_and_latency() -> None:
    metrics = RequestMetrics()

    metrics.record(status_code=200, latency_ms=4.0)
    metrics.record(status_code=503, latency_ms=8.0)

    assert metrics.snapshot() == {
        "requests_total": 2,
        "requests_success_total": 1,
        "requests_failure_total": 1,
        "latency_ms_total": 12.0,
        "latency_ms_average": 6.0,
    }


def test_metrics_start_empty() -> None:
    metrics = RequestMetrics()

    assert metrics.snapshot() == {
        "requests_total": 0,
        "requests_success_total": 0,
        "requests_failure_total": 0,
        "latency_ms_total": 0.0,
        "latency_ms_average": 0.0,
    }
