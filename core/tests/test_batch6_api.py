from __future__ import annotations

from fastapi.testclient import TestClient

from aura_core.application.api import create_api
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig


class StubTransport:
    def post_json(self, endpoint: str, payload: dict, timeout: float) -> dict:
        return {
            "model": "qwen3-test",
            "message": {"role": "assistant", "content": "Kısa ve doğal yanıt."},
            "done": True,
        }

    def get_json(self, endpoint: str, timeout: float) -> dict:
        return {"models": []}


def make_client() -> TestClient:
    app = create_api(
        RuntimeConfig(runtime="ollama", model="qwen3-test", temperature=0.2, max_tokens=64),
        backend_config=BackendConfig(endpoint="http://127.0.0.1:11434", timeout=2.0),
        transport=StubTransport(),
    )
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "local_owner"
    return TestClient(app, headers={"Authorization": "Bearer " + "t" * 40})


def test_simulation_endpoint_returns_plan_and_non_executing_analysis() -> None:
    client = make_client()
    response = client.post(
        "/api/reasoning/simulate",
        json={"directive": "Araştırma yap ve sonuçları karşılaştırıp özetle."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["simulation"]["simulator_version"] == "1.0"
    assert body["simulation"]["recommendation"] in {
        "do_not_execute", "review_before_execution", "ready_for_authorization_check"
    }
    assert "does not execute tools" in body["simulation"]["limitations"]


def test_runtime_telemetry_and_concurrency_endpoints_are_available() -> None:
    client = make_client()
    telemetry = client.get("/api/runtime/telemetry")
    concurrency = client.get("/api/runtime/concurrency")
    assert telemetry.status_code == 200
    assert telemetry.json()["status"] in {"ok", "unavailable"}
    assert concurrency.status_code == 200
    assert concurrency.json()["active"] == 0
    assert concurrency.json()["capacity"] >= 1


def test_assistant_response_uses_context_synthesizer_and_offloaded_inference() -> None:
    client = make_client()
    response = client.post("/api/assistant/respond", json={"message": "Merhaba."})
    assert response.status_code == 200
    assert response.json()["assistant_reply"] == "Kısa ve doğal yanıt."
    assert client.get("/api/runtime/concurrency").json()["completed"] == 1
