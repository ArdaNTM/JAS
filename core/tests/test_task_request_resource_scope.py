from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from aura_core.application.api import create_api
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig


class StubTransport:
    def post_json(self, endpoint: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        return {
            "model": "qwen3:4b-instruct-2507-q4_K_M",
            "message": {"role": "assistant", "content": "ok"},
            "done": True,
        }

    def get_json(self, endpoint: str, timeout: float) -> dict[str, Any]:
        return {"models": []}


class RecordingTaskService:
    def __init__(self) -> None:
        self.submitted = None

    async def submit(self, submitted):
        self.submitted = submitted
        return SimpleNamespace(
            plan_id=submitted.plan.plan_id,
            state="succeeded",
            steps=[],
        )


def test_task_api_preserves_requested_resource_scope() -> None:
    config = RuntimeConfig(
        runtime="ollama",
        model="qwen3:4b-instruct-2507-q4_K_M",
        temperature=0.7,
        max_tokens=32,
    )
    backend = BackendConfig(endpoint="http://127.0.0.1:11434", timeout=30.0)
    task_service = RecordingTaskService()
    app = create_api(
        config,
        backend_config=backend,
        transport=StubTransport(),
        task_service=task_service,
    )
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "local_owner"

    with TestClient(app) as client:
        response = client.post(
            "/api/tasks",
            headers={"Authorization": f"Bearer {'t' * 40}"},
            json={
                "task_id": "scope-regression-test",
                "principal_id": "untrusted-body-principal",
                "title": "Verify resource scope propagation",
                "resource_scope": "workspace:test-scope",
                "steps": [{
                    "step_id": "fetch",
                    "capability_id": "internet.fetch",
                    "operation_id": "internet.fetch",
                    "tool_name": "fetch",
                    "risk_level": "low",
                    "arguments": {"url": "https://example.com"},
                }],
            },
        )

    assert response.status_code == 200, response.text
    assert task_service.submitted is not None
    assert task_service.submitted.task.principal_id == "local_owner"
    assert task_service.submitted.task.resource_scope == "workspace:test-scope"
