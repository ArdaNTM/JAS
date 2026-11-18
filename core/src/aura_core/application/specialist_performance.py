"""Read-only bounded response-latency observations from scoped Swarm events.

These are event-to-event durations, NOT verified work times, tool success,
independently attested clocks, or PermissionEngine authorization.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from aura_core.kernel.events import KernelEvent

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}\Z", re.ASCII)
_ROLES = frozenset({"coder", "researcher"})
_DECISIONS = frozenset({"allow", "deny", "require_approval", "defer"})


@dataclass(frozen=True, slots=True)
class SpecialistResponseMetrics:
    role: str
    requests_observed: int
    responses_observed: int
    pending_without_response: int
    denied_responses: int
    approval_required_responses: int
    p50_response_ms: float | None
    p95_response_ms: float | None
    untrusted_events: bool = True
    tool_success_verified: bool = False


@dataclass(frozen=True, slots=True)
class SpecialistPerformanceReport:
    specialists: tuple[SpecialistResponseMetrics, ...]
    event_count_scoped: int
    authorization_checked: bool = False
    clock_provenance_verified: bool = False
    actual_execution_verified: bool = False
    performance_certified: bool = False


def _scope(value: str) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise ValueError("invalid exact event scope")
    return value


def _time(value: datetime) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware event timestamp required")
    return value.astimezone(UTC)


def _percentile_ms(values: list[float], proportion: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * proportion) - 1)
    return round(ordered[index], 3)


def evaluate_specialist_responses(
    events: tuple[KernelEvent, ...], *,
    principal_id: str, task_id: str,
) -> SpecialistPerformanceReport:
    """Pair bounded exact-scope request/response events in observed order."""
    principal, task = _scope(principal_id), _scope(task_id)
    if type(events) is not tuple or len(events) > 512:
        raise ValueError("bounded immutable event sequence required")
    pending: dict[int, tuple[str, datetime]] = {}
    finished: set[int] = set()
    requested: dict[str, int] = defaultdict(int)
    responses: dict[str, int] = defaultdict(int)
    denied: dict[str, int] = defaultdict(int)
    approval: dict[str, int] = defaultdict(int)
    durations: dict[str, list[float]] = defaultdict(list)
    scoped_count = 0
    for event in events:
        if type(event) is not KernelEvent:
            raise ValueError("KernelEvent required")
        if event.event_type not in {"SwarmStepRequested", "SwarmStepCompleted"}:
            continue
        if event.source_component != "aura.swarm":
            continue
        data = event.payload
        if (
            event.correlation_id != task
            or data.get("principal_id") != principal
            or data.get("task_id") != task
        ):
            continue
        scoped_count += 1
        index = data.get("index")
        role = data.get("role")
        if type(index) is not int or not 0 <= index <= 31:
            raise ValueError("invalid scoped step index")
        if type(role) is not str or role not in _ROLES:
            raise ValueError("invalid scoped specialist role")
        instant = _time(event.timestamp)
        if event.event_type == "SwarmStepRequested":
            if index in pending or index in finished:
                raise ValueError("duplicate scoped step request")
            pending[index] = (role, instant)
            requested[role] += 1
        else:
            if index not in pending or index in finished:
                raise ValueError("unpaired or duplicate scoped response")
            expected_role, began = pending[index]
            if expected_role != role:
                raise ValueError("specialist role changed within a step")
            decision = data.get("decision")
            if type(decision) is not str or decision not in _DECISIONS:
                raise ValueError("invalid Gateway response decision")
            duration_ms = (instant - began).total_seconds() * 1000
            if not math.isfinite(duration_ms) or not 0 <= duration_ms <= 3_600_000:
                raise ValueError("invalid or implausible event time ordering")
            durations[role].append(duration_ms)
            responses[role] += 1
            denied[role] += decision == "deny"
            approval[role] += decision == "require_approval"
            finished.add(index)

    metrics: list[SpecialistResponseMetrics] = []
    for role in sorted(requested):
        metrics.append(SpecialistResponseMetrics(
            role=role,
            requests_observed=requested[role],
            responses_observed=responses[role],
            pending_without_response=requested[role] - responses[role],
            denied_responses=denied[role],
            approval_required_responses=approval[role],
            p50_response_ms=_percentile_ms(durations[role], 0.50),
            p95_response_ms=_percentile_ms(durations[role], 0.95),
        ))
    return SpecialistPerformanceReport(
        specialists=tuple(metrics), event_count_scoped=scoped_count,
    )
