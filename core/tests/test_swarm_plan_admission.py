"""All-or-nothing swarm admission: invalid later steps execute nothing."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
import pytest

from aura_core.application.swarm_orchestration import SpecialistStep, SwarmOrchestrator
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel


class FakeGateway:
    def __init__(self, decisions=()):
        self.calls = []
        self.decisions = iter(decisions)

    async def invoke(self, request):
        self.calls.append(request)
        return SimpleNamespace(decision=next(self.decisions, AuthorizationDecision.ALLOW))


class FakeEvents:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


def step(*, role="researcher", arguments=None):
    return SpecialistStep(
        role, "internet.search", "internet.search", "public-web",
        "search", arguments if arguments is not None else {"query": "information"},
    )


def test_invalid_later_role_prevents_earlier_tool_dispatch():
    gateway, events = FakeGateway(), FakeEvents()
    with pytest.raises(ValueError):
        asyncio.run(SwarmOrchestrator(gateway=gateway, event_bus=events).execute(
            principal_id="owner", task_id="task-1",
            steps=(step(), step(role="root")),
        ))
    assert gateway.calls == []
    assert events.events == []


def test_valid_plan_uses_gateway_authorization_boundary():
    gateway, events = FakeGateway(), FakeEvents()
    outputs = asyncio.run(SwarmOrchestrator(gateway=gateway, event_bus=events).execute(
        principal_id="owner", task_id="task-2",
        steps=(step(), step(role="coder")),
    ))
    assert len(outputs) == len(gateway.calls) == 2
    assert len(events.events) == 4
    assert all(call.principal_id == "owner" for call in gateway.calls)
    assert all(call.risk_level is RiskLevel.MEDIUM for call in gateway.calls)


def test_denial_ends_execution_before_second_step():
    gateway = FakeGateway((AuthorizationDecision.DENY,))
    outputs = asyncio.run(SwarmOrchestrator(gateway=gateway, event_bus=FakeEvents()).execute(
        principal_id="owner", task_id="task-3",
        steps=(step(), step()),
    ))
    assert len(outputs) == len(gateway.calls) == 1


@pytest.mark.parametrize("args", [
    {"query": float("nan")}, {"query": object()},
    {"query": "x" * 33000}, {"query": [1] * 1001},
    {"query": {"nested": object()}},
])
def test_bad_arguments_prevent_any_dispatch(args):
    gateway, events = FakeGateway(), FakeEvents()
    with pytest.raises(ValueError):
        asyncio.run(SwarmOrchestrator(gateway=gateway, event_bus=events).execute(
            principal_id="owner", task_id="task-4",
            steps=(step(), step(arguments=args)),
        ))
    assert gateway.calls == []
    assert events.events == []


def test_cycle_and_boolean_max_steps_rejected():
    loop = {}
    loop["again"] = loop
    gateway, events = FakeGateway(), FakeEvents()
    with pytest.raises(ValueError):
        asyncio.run(SwarmOrchestrator(gateway=gateway, event_bus=events).execute(
            principal_id="owner", task_id="task-5",
            steps=(step(), step(arguments=loop)),
        ))
    assert gateway.calls == []
    with pytest.raises(ValueError):
        SwarmOrchestrator(gateway=gateway, event_bus=events, max_steps=True)
