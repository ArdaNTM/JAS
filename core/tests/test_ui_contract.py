from __future__ import annotations

from fastapi.testclient import TestClient

from aura_core.application.api import create_api
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig


class StubTransport:
    def post_json(self, endpoint: str, payload: dict, timeout: float) -> dict:
        return {
            "model": "provider-test",
            "message": {"role": "assistant", "content": "stub"},
            "done": True,
        }

    def get_json(self, endpoint: str, timeout: float) -> dict:
        return {"models": []}


def make_client() -> TestClient:
    app = create_api(
        RuntimeConfig(runtime="ollama", model="provider-test", temperature=0, max_tokens=64),
        backend_config=BackendConfig(endpoint="http://127.0.0.1:11434", timeout=1),
        transport=StubTransport(),
    )
    return TestClient(app)


def test_ui_contract_is_provider_neutral_and_describes_operation_states() -> None:
    with make_client() as client:
        response = client.get("/api/ui/v1/contract")

    assert response.status_code == 200
    body = response.json()
    assert body["contract_version"] == "1.0"
    assert body["request_id_header"] == "X-Request-ID"
    assert "awaiting_approval" in body["operation_states"]
    assert "succeeded" in body["operation_states"]
    assert "ollama" not in str(body["security"]).lower()
    assert "MCP Gateway" in body["security"]["tool_execution"]


def test_validation_errors_include_stable_envelope_and_keep_legacy_detail() -> None:
    with make_client() as client:
        response = client.post("/api/tools/proposals", json={})

    assert response.status_code == 422
    body = response.json()
    assert isinstance(body["detail"], list)
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["retryable"] is False
    assert body["error"]["request_id"]
    assert response.headers["X-Request-ID"] == body["error"]["request_id"]
    assert all("input" not in item for item in body["error"]["details"])
