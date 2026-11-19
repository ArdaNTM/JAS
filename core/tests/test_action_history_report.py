"""#98/#117: actual Swarm EventBus observations without payload disclosure."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from aura_core.application.action_history import (
    project_swarm_history, render_action_history,
)
from aura_core.application.swarm_orchestration import SpecialistStep, SwarmOrchestrator
from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.kernel.permissions import AuthorizationDecision


class FakeGateway:
    def __init__(self, decisions):
        self.decisions = iter(decisions)
        self.calls = []

    async def invoke(self, request):
        self.calls.append(request)
        return SimpleNamespace(decision=next(self.decisions))


def step():
    return SpecialistStep(
        role="researcher", capability_id="web.search",
        operation_id="search", resource_scope="public", tool_name="search",
        arguments={"query": "example"},
    )


def capture_swarm(decisions):
    async def run():
        bus = EventBus()
        output = []
        bus.subscribe("*", output.append)
        gateway = FakeGateway(decisions)
        await SwarmOrchestrator(gateway=gateway, event_bus=bus).execute(
            principal_id="alice", task_id="task-1", steps=(step(), step())
        )
        for _ in range(4):
            await bus.dispatch_once()
        return output, gateway
    return asyncio.run(run())


def test_real_gateway_allow_and_deny_observations():
    events, gateway = capture_swarm([
        AuthorizationDecision.ALLOW, AuthorizationDecision.DENY,
    ])
    report = project_swarm_history(events, principal_id="alice", task_id="task-1")
    assert len(gateway.calls) == 2
    assert report.requested_count == report.response_count == 2
    assert report.denied_count == 1
    assert [entry.gateway_decision for entry in report.steps] == ["allow", "deny"]
    assert not report.execution_success_verified
    assert not report.owner_approval_verified
    assert not report.authorization_checked
    assert not report.report_delivered
    assert all(not step.execution_success_verified for step in report.steps)


def test_gateway_approval_is_not_claimed_as_owner_receipt():
    events, gateway = capture_swarm([AuthorizationDecision.REQUIRE_APPROVAL])
    report = project_swarm_history(events, principal_id="alice", task_id="task-1")
    assert len(gateway.calls) == 1
    assert report.pending_approval_count == 1
    assert report.owner_approval_verified is False
    assert report.response_count == 1


def event(kind, *, principal="alice", task="t1", index=0, decision="allow", secret=None):
    payload = {
        "principal_id": principal, "task_id": task, "index": index,
        "secret": secret,
    }
    if kind == "SwarmStepCompleted":
        payload["decision"] = decision
    return KernelEvent(
        event_type=kind, source_component="aura.swarm",
        correlation_id=task, payload=payload,
    )


def test_scope_isolation_and_payload_secrets_never_rendered():
    records = [
        event("SwarmStepRequested", principal="other", secret="SECRET-other"),
        event("SwarmStepRequested", secret="SECRET-private"),
        event("SwarmStepCompleted", secret="SECRET-private"),
        event("SwarmStepCompleted", principal="other", secret="SECRET-other"),
    ]
    report = project_swarm_history(records, principal_id="alice", task_id="t1")
    assert report.requested_count == report.response_count == 1
    output = render_action_history(report)
    assert "SECRET" not in repr(report)
    assert "SECRET" not in output
    assert "alice" not in output
    assert "other" not in output
    assert "Gateway replies do not prove tool" in output


def test_partial_requested_step_is_not_claimed_successful():
    report = project_swarm_history(
        [event("SwarmStepRequested")], principal_id="alice", task_id="t1"
    )
    assert report.incomplete_count == 1
    assert report.steps[0].gateway_decision is None
    assert "no response" in render_action_history(report)


@pytest.mark.parametrize("events", [
    [event("SwarmStepCompleted")],
    [event("SwarmStepRequested"), event("SwarmStepRequested")],
    [event("SwarmStepRequested"), event("SwarmStepCompleted", decision="root")],
    [event("SwarmStepRequested", index=True)],
    [object()],
])
def test_malformed_scoped_event_provenance_rejected(events):
    with pytest.raises(ValueError):
        project_swarm_history(events, principal_id="alice", task_id="t1")


def test_input_scope_and_budget_fail_closed():
    with pytest.raises(ValueError):
        project_swarm_history([], principal_id="alice", task_id="../evil")
    with pytest.raises(ValueError):
        project_swarm_history([], principal_id="alice", task_id="task", max_events=True)
    with pytest.raises(ValueError):
        project_swarm_history(
            [event("SwarmStepRequested")] * 513,
            principal_id="alice", task_id="t1",
        )
    with pytest.raises(ValueError):
        render_action_history({"requested_count": 1})
