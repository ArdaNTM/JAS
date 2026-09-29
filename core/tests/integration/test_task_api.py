from fastapi.testclient import TestClient

from aura_core.agent.runtime import ExecutionResult, PlanState, StepResult, StepState
from aura_core.application.api import create_api
from aura_core.application.tasks import AgentTaskService
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig


class Runtime:
    def __init__(self) -> None:
        self.calls = []

    async def execute(self, task, plan):
        self.calls.append((task, plan))
        return ExecutionResult(plan.plan_id, PlanState.SUCCEEDED, tuple(StepResult(step.step_id, StepState.SUCCEEDED, 1, {"content": "ok"}) for step in plan.steps), 0.01)


class Transport:
    def post_json(self, endpoint, payload, timeout):
        return {"model": "test", "message": {"content": "ok"}, "done": True}
    def get_json(self, endpoint, timeout):
        return {"models": [{"name": "test"}]}


def test_task_endpoint_composes_http_to_agent_runtime_without_provider_access() -> None:
    runtime = Runtime()
    app = create_api(RuntimeConfig(model="test"), BackendConfig(endpoint="http://test", timeout=1), Transport(), AgentTaskService(runtime))
    response = TestClient(app).post("/api/tasks", json={
        "task_id": "task-1", "principal_id": "agent:web", "title": "Read", "resource_scope": "D:/workspace",
        "steps": [{"step_id": "one", "capability_id": "filesystem.read", "operation_id": "filesystem.read_file", "tool_name": "read_file", "risk_level": "low"}],
    })
    assert response.status_code == 200
    assert response.json()["state"] == "succeeded"
    assert runtime.calls[0][1].steps[0].tool_name == "read_file"
