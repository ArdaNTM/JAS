from datetime import datetime

import pytest

from aura_core.observability.pipeline_trace import PipelineTrace


def test_trace_records_completed_stage_metadata() -> None:
    trace = PipelineTrace("request-123")

    trace.start_stage("planning")
    record = trace.finish_stage("planning")

    assert record.name == "planning"
    assert record.duration_ms >= 0
    assert record.outcome == "success"
    datetime.fromisoformat(record.started_at)

    snapshot = trace.snapshot()
    assert snapshot["request_id"] == "request-123"
    assert snapshot["stage_count"] == 1
    assert snapshot["active_stages"] == []
    assert snapshot["completed_stages"][0]["name"] == "planning"


def test_trace_supports_failure_outcome() -> None:
    trace = PipelineTrace("request-456")
    trace.start_stage("execution")

    record = trace.finish_stage("execution", outcome="failure")

    assert record.outcome == "failure"


def test_trace_rejects_blank_request_id() -> None:
    with pytest.raises(ValueError, match="request_id"):
        PipelineTrace(" ")


def test_trace_rejects_duplicate_active_stage() -> None:
    trace = PipelineTrace("request-123")
    trace.start_stage("planning")

    with pytest.raises(ValueError, match="already active"):
        trace.start_stage("planning")


def test_trace_rejects_finish_of_inactive_stage() -> None:
    trace = PipelineTrace("request-123")

    with pytest.raises(ValueError, match="not active"):
        trace.finish_stage("planning")


def test_trace_rejects_unsupported_outcome() -> None:
    trace = PipelineTrace("request-123")
    trace.start_stage("planning")

    with pytest.raises(ValueError, match="outcome"):
        trace.finish_stage("planning", outcome="unknown")


def test_trace_does_not_expose_unrelated_payloads() -> None:
    trace = PipelineTrace("request-123")
    trace.start_stage("planning")

    snapshot = trace.snapshot()

    assert set(snapshot) == {
        "request_id",
        "completed_stages",
        "active_stages",
        "stage_count",
    }
