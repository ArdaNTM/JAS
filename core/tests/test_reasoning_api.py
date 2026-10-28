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
    app = create_api(config, backend_config=backend)
    app.state.http_bearer_token = "test-token-" + "x" * 40
    app.state.http_principal_id = "local_owner"
    return TestClient(app)


def test_reasoning_plan_endpoint_returns_plan_without_execution() -> None:
    response = make_client().post(
        "/api/reasoning/plan",
        json={"directive": "Araştır ve sonuçları karşılaştır."},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].lower() == "application/json; charset=utf-8"
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



def test_reasoning_plan_preserves_turkish_utf8_json_bytes() -> None:
    directive = "Yapay zekâ modellerini araştır ve sonuçları karşılaştırıp özetle."
    request_body = ('{"directive": "' + directive + '"}').encode("utf-8")
    response = make_client().post(
        "/api/reasoning/plan",
        content=request_body,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].lower() == "application/json; charset=utf-8"
    assert response.json()["directive"] == directive
    assert directive.encode("utf-8") in response.content
    assert "Ã¢" not in response.content.decode("utf-8")
    assert "Å" not in response.content.decode("utf-8")


def test_reasoning_execute_requires_runtime_instead_of_bypassing_gateway() -> None:
    response = make_client().post(
        "/api/reasoning/execute",
        json={"directive": "Yapay zekâ modellerini araştır."},
        headers={"Authorization": "Bearer " + "test-token-" + "x" * 40},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Agent runtime is not configured"
