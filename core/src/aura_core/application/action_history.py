"""Read-only, identity-scoped explanatory views of existing Swarm KernelEvents.

An event is an observation, NOT a cryptographic receipt or evidence a tool
actually executed. Caller must authenticate scope before passing events.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from aura_core.kernel.events import KernelEvent
from aura_core.kernel.permissions import AuthorizationDecision

_EVENT_TYPES = frozenset({"SwarmStepRequested", "SwarmStepCompleted"})
_DECISIONS = frozenset(decision.value for decision in AuthorizationDecision)


@dataclass(frozen=True, slots=True)
class ActionStepObservation:
    index: int
    requested_observed: bool
    response_observed: bool
    gateway_decision: str | None
    execution_success_verified: bool = False


@dataclass(frozen=True, slots=True)
class ActionHistoryReport:
    steps: tuple[ActionStepObservation, ...]
    requested_count: int
    response_count: int
    denied_count: int
    pending_approval_count: int
    incomplete_count: int
    untrusted_events: bool = True
    owner_approval_verified: bool = False
    execution_success_verified: bool = False
    authorization_checked: bool = False
    report_delivered: bool = False


def _identity(value: str) -> str:
    if (
        type(value) is not str or not 1 <= len(value) <= 200
        or value != value.strip()
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError("invalid exact event identity")
    return value


def project_swarm_history(
    events: Sequence[KernelEvent], *, principal_id: str,
    task_id: str, max_events: int = 512,
) -> ActionHistoryReport:
    """Reduce a preauthorized bounded stream of events without dispatch.

    Events for another principal/task are silently omitted. Malformed records
    that claim the requested identity fail closed rather than being treated as
    trustworthy permission/skill evidence.
    """
    principal = _identity(principal_id)
    task = _identity(task_id)
    if type(max_events) is not int or not 1 <= max_events <= 512:
        raise ValueError("max_events must be 1..512")
    if not isinstance(events, (list, tuple)) or len(events) > max_events:
        raise ValueError("bounded event list required")
    state: dict[int, str | None] = {}
    completed: set[int] = set()
    for event in events:
        if type(event) is not KernelEvent:
            raise ValueError("KernelEvent records required")
        if event.event_type not in _EVENT_TYPES or event.source_component != "aura.swarm":
            continue
        data = event.payload
        if (
            event.correlation_id != task
            or data.get("principal_id") != principal
            or data.get("task_id") != task
        ):
            continue
        index = data.get("index")
        if type(index) is not int or not 0 <= index < 32:
            raise ValueError("invalid scoped swarm step index")
        if event.event_type == "SwarmStepRequested":
            if index in state:
                raise ValueError("duplicate scoped step request")
            state[index] = None
        else:
            if index not in state or index in completed:
                raise ValueError("unpaired or duplicate scoped step response")
            decision = data.get("decision")
            if type(decision) is not str or decision not in _DECISIONS:
                raise ValueError("invalid scoped Gateway decision")
            state[index] = decision
            completed.add(index)
    steps = tuple(
        ActionStepObservation(
            index=index, requested_observed=True,
            response_observed=index in completed,
            gateway_decision=state[index],
        )
        for index in sorted(state)
    )
    return ActionHistoryReport(
        steps=steps,
        requested_count=len(state),
        response_count=len(completed),
        denied_count=sum(row.gateway_decision == "deny" for row in steps),
        pending_approval_count=sum(
            row.gateway_decision == "require_approval" for row in steps
        ),
        incomplete_count=len(state) - len(completed),
    )


def render_action_history(report: ActionHistoryReport) -> str:
    """Build a bounded plaintext/Markdown report without raw event payloads."""
    if type(report) is not ActionHistoryReport:
        raise ValueError("ActionHistoryReport required")
    lines = [
        "# Swarm action observations",
        "",
        "Untrusted event observations only. Gateway replies do not prove tool "
        "execution, Owner approval or success.",
        "",
        f"Requested steps: {report.requested_count}",
        f"Observed Gateway responses: {report.response_count}",
        f"Denied responses: {report.denied_count}",
        f"Approval-needed responses: {report.pending_approval_count}",
        f"No response observed: {report.incomplete_count}",
        "",
    ]
    for step in report.steps:
        response = step.gateway_decision if step.response_observed else "no response"
        lines.append(f"- Step {step.index}: Gateway response observed: {response}")
    return "\n".join(lines) + "\n"
