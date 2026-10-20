import pytest
from fastapi.testclient import TestClient

from aura_core.application.api import create_api
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig


def make_client() -> TestClient:
    config = RuntimeConfig(
        runtime="ollama",
        model="qwen3:4b-instruct-2507-q4_K_M",
        temperature=0.7,
        max_tokens=32,
    )
    backend = BackendConfig(endpoint="http://127.0.0.1:11434", timeout=30.0)
    return TestClient(create_api(config, backend_config=backend))


def test_reasoning_plan_endpoint_returns_plan_without_execution() -> None:
    response = make_client().post(
        "/api/reasoning/plan",
        json={"directive": "Araştır ve sonuçları karşılaştır."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["execution_started"] is False
    assert body["steps"][0]["kind"] == "capability_request"
    assert body["steps"][0]["requires_authorization"] is True
    assert body["steps"][1]["depends_on"] == ["research"]


def test_reasoning_plan_endpoint_rejects_unsupported_directive() -> None:
    response = make_client().post(
        "/api/reasoning/plan",
        json={"directive": "Kahvemi hazırla."},
    )
    assert response.status_code == 422
