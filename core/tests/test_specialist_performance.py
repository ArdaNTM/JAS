"""Feature #63: real KernelEvent pairing, latencies, scope & denial tests."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aura_core.application.specialist_performance import (
    evaluate_specialist_responses,
)
from aura_core.kernel.events import KernelEvent

START = datetime(2026, 11, 16, 12, tzinfo=UTC)


def event(kind, index, *, offset_ms=0, role="coder",
          principal="owner", task="task-1", decision="allow", timestamp=None):
    payload = {
        "principal_id": principal, "task_id": task, "role": role,
        "index": index,
    }
    if kind == "SwarmStepCompleted":
        payload["decision"] = decision
    return KernelEvent(
        event_type=kind, source_component="aura.swarm",
        correlation_id=task, payload=payload,
        timestamp=timestamp if timestamp is not None
        else START + timedelta(milliseconds=offset_ms),
    )


def test_real_nearest_rank_latency_and_denial_not_success():
    events = tuple(
        item
        for index in range(5)
        for item in (
            event("SwarmStepRequested", index, offset_ms=index * 1000),
            event("SwarmStepCompleted", index,
                  offset_ms=index * 1000 + (index + 1) * 100,
                  decision="deny" if index == 4 else "allow"),
        )
    )
    report = evaluate_specialist_responses(
        events, principal_id="owner", task_id="task-1"
    )
    assert report.event_count_scoped == 10
    metrics = report.specialists[0]
    assert metrics.requests_observed == metrics.responses_observed == 5
    assert metrics.p50_response_ms == 300
    assert metrics.p95_response_ms == 500
    assert metrics.denied_responses == 1
    assert metrics.pending_without_response == 0
    assert metrics.untrusted_events and not metrics.tool_success_verified
    assert not report.authorization_checked
    assert not report.actual_execution_verified
    assert not report.clock_provenance_verified
    assert not report.performance_certified


def test_role_partitioning_and_incomplete_requests():
    records = (
        event("SwarmStepRequested", 0, role="coder"),
        event("SwarmStepCompleted", 0, role="coder", offset_ms=50),
        event("SwarmStepRequested", 1, role="researcher", offset_ms=100),
    )
    report = evaluate_specialist_responses(
        records, principal_id="owner", task_id="task-1"
    )
    assert [item.role for item in report.specialists] == ["coder", "researcher"]
    assert report.specialists[0].p95_response_ms == 50
    assert report.specialists[1].p95_response_ms is None
    assert report.specialists[1].pending_without_response == 1


def test_other_scopes_do_not_pollute_metrics():
    records = (
        event("SwarmStepRequested", 0, principal="other"),
        event("SwarmStepCompleted", 0, principal="other"),
        event("SwarmStepRequested", 1, task="another-task"),
    )
    report = evaluate_specialist_responses(
        records, principal_id="owner", task_id="task-1"
    )
    assert report.event_count_scoped == 0
    assert report.specialists == ()


@pytest.mark.parametrize("records", [
    (event("SwarmStepCompleted", 0),),
    (event("SwarmStepRequested", 0),
     event("SwarmStepRequested", 0)),
    (event("SwarmStepRequested", 0),
     event("SwarmStepCompleted", 0, role="researcher")),
    (event("SwarmStepRequested", True),),
    (event("SwarmStepRequested", 0, role="root"),),
    (event("SwarmStepRequested", 0),
     event("SwarmStepCompleted", 0, decision="pretend-success")),
    (event("SwarmStepRequested", 0),
     event("SwarmStepCompleted", 0, offset_ms=-1)),
    (event("SwarmStepRequested", 0),
     event("SwarmStepCompleted", 0, offset_ms=3_600_001)),
    (event("SwarmStepRequested", 0,
           timestamp=datetime(2026, 11, 16)),),
])
def test_invalid_scoped_event_or_clock_fails_closed(records):
    with pytest.raises(ValueError):
        evaluate_specialist_responses(
            records, principal_id="owner", task_id="task-1"
        )


def test_type_confusion_and_event_count_bounds():
    with pytest.raises(ValueError):
        evaluate_specialist_responses(
            [event("SwarmStepRequested", 0)], principal_id="owner", task_id="task-1",
        )
    with pytest.raises(ValueError):
        evaluate_specialist_responses(
            (object(),), principal_id="owner", task_id="task-1",
        )
    with pytest.raises(ValueError):
        evaluate_specialist_responses(
            tuple(event("SwarmStepRequested", i % 32) for i in range(513)),
            principal_id="owner", task_id="task-1",
        )
    with pytest.raises(ValueError):
        evaluate_specialist_responses(
            (), principal_id="../other", task_id="task-1",
        )
