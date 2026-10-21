from __future__ import annotations

from fastapi.testclient import TestClient

from aura_core.application.api import create_api
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig


class StubTransport:
    def post_json(self, endpoint, payload, timeout):
        return {
            "model": "qwen3:4b-instruct-2507-q4_K_M",
            "message": {"role": "assistant", "content": "OK"},
            "done": True,
        }


def make_client() -> TestClient:
    return TestClient(create_api(
        RuntimeConfig(runtime="ollama", model="qwen3:4b-instruct-2507-q4_K_M", temperature=0.7, max_tokens=32),
        backend_config=BackendConfig(endpoint="http://127.0.0.1:11434", timeout=30.0),
        transport=StubTransport(),
    ))


def test_autonomy_plan_validation_is_local_and_never_executes():
    response = make_client().post("/api/autonomy/plan/validate", json={
        "nodes": [
            {"task_id": "observe", "title": "Kanıtları topla", "kind": "observe"},
            {"task_id": "verify", "title": "Sonucu doğrula", "depends_on": ["observe"], "kind": "verify", "requires_approval": True},
        ],
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["execution_started"] is False
    assert payload["nodes"][1]["requires_approval"] is True
    assert "MCPGateway" in payload["authorization_boundary"]


def test_autonomy_plan_validation_rejects_cycles():
    response = make_client().post("/api/autonomy/plan/validate", json={
        "nodes": [
            {"task_id": "a", "title": "A", "depends_on": ["b"]},
            {"task_id": "b", "title": "B", "depends_on": ["a"]},
        ],
    })
    assert response.status_code == 422


def test_autonomy_experiment_returns_pure_result_without_side_effects():
    response = make_client().post("/api/autonomy/experiment", json={
        "expression": "value * 2",
        "data": {"value": 21},
    })
    assert response.status_code == 200
    assert response.json()["result"] == 42
    assert response.json()["arbitrary_code_executed"] is False
    assert response.json()["tool_execution_performed"] is False
    assert response.json()["memory_mutated"] is False


def test_autonomy_experiment_rejects_arbitrary_code():
    response = make_client().post("/api/autonomy/experiment", json={
        "expression": "__import__('os').system('whoami')",
        "data": {},
    })
    assert response.status_code == 422
