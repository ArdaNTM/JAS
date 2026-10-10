import asyncio

from aura_core.agent.runtime import AgentExecutor, Plan, PlanState, PlanStep, Task, _request_id_context
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.mcp.gateway import MCPGatewayResponse
from aura_core.kernel.events import EventBus


class Gateway:
    def __init__(self, decisions: list[AuthorizationDecision]) -> None:
        self.decisions = decisions
        self.requests = []

    async def invoke(self, request):
        self.requests.append(request)
        decision = self.decisions.pop(0)
        return MCPGatewayResponse(decision, {"ok": True} if decision is AuthorizationDecision.ALLOW else None, "mcp:test", request.tool_name, "allowed" if decision is AuthorizationDecision.ALLOW else "denied")


def task() -> Task:
    return Task("task-1", "agent:test", "Read", "D:\\workspace")


def step(identifier: str, dependencies: frozenset[str] = frozenset()) -> PlanStep:
    return PlanStep(identifier, "filesystem.read", "filesystem.read_file", "read_file", RiskLevel.LOW, depends_on=dependencies)


def test_executor_routes_each_executable_step_through_gateway() -> None:
    gateway = Gateway([AuthorizationDecision.ALLOW, AuthorizationDecision.ALLOW])
    plan = Plan("plan-1", "task-1", (step("first"), step("second", frozenset({"first"}))))

    result = asyncio.run(AgentExecutor(gateway).execute(task(), plan))

    assert result.state is PlanState.SUCCEEDED
    assert [request.tool_name for request in gateway.requests] == ["read_file", "read_file"]


def test_failed_authorization_stops_dependent_step_without_a_second_gateway_call() -> None:
    gateway = Gateway([AuthorizationDecision.DENY])
    plan = Plan("plan-1", "task-1", (step("first"), step("second", frozenset({"first"}))))

    result = asyncio.run(AgentExecutor(gateway).execute(task(), plan))

    assert result.state is PlanState.FAILED
    assert len(gateway.requests) == 1
    assert result.steps[1].reason == "Dependency did not succeed"


def test_executor_events_include_request_id_metadata_without_changing_correlation() -> None:
    gateway = Gateway([AuthorizationDecision.ALLOW])
    bus = EventBus()
    received = []
    bus.subscribe("*", received.append)
    plan = Plan("plan-1", "task-1", (step("first"),))
    token = _request_id_context.set("request-trace-test-123")
    try:
        result = asyncio.run(AgentExecutor(gateway, bus).execute(task(), plan))
    finally:
        _request_id_context.reset(token)

    assert result.state is PlanState.SUCCEEDED
    assert asyncio.run(bus.dispatch_once()) is True
    assert asyncio.run(bus.dispatch_once()) is True
    assert len(received) == 2
    assert all(event.metadata["request_id"] == "request-trace-test-123" for event in received)
    assert all(event.correlation_id == plan.plan_id for event in received)
