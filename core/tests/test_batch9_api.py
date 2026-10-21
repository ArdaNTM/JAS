from __future__ import annotations

from fastapi.testclient import TestClient

from aura_core.application.api import create_api
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig


class StubTransport:
    def post_json(self, endpoint: str, payload: dict, timeout: float) -> dict:
        return {
            "model": "qwen3-test",
            "message": {"role": "assistant", "content": "local inference stub"},
            "done": True,
        }

    def get_json(self, endpoint: str, timeout: float) -> dict:
        return {"models": []}


def client() -> TestClient:
    app = create_api(
        RuntimeConfig(runtime="ollama", model="qwen3-test", temperature=0, max_tokens=128),
        backend_config=BackendConfig(endpoint="http://127.0.0.1:11434", timeout=2),
        transport=StubTransport(),
    )
    return TestClient(app)


def test_candidate_tool_endpoint_never_enables_execution() -> None:
    with client() as test_client:
        response = test_client.post("/api/tools/proposals", json={
            "tool_name": "normalize_text",
            "description": "Normalize a text value.",
            "source_code": "def run(data):\n    return {\"value\": data.get(\"value\", \"\").strip()}\n",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
        })
        assert response.status_code == 200
        body = response.json()
        assert body["validation"]["valid"] is True
        assert body["manifest"]["execution_enabled"] is False
        assert body["manifest"]["registration_enabled"] is False


def test_prefetch_endpoint_only_emits_approval_proposal(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AURA_PREFETCH_DB", str(tmp_path / "api-prefetch.sqlite3"))
    with client() as test_client:
        result = None
        for _ in range(3):
            response = test_client.post("/api/prefetch/observe", json={
                "principal_id": "local-user",
                "event_key": "morning_start",
                "capability_id": "calendar.read",
                "hour_local": 8,
            })
            assert response.status_code == 200
            result = response.json()
        assert result is not None
        assert result["execution_performed"] is False
        assert result["proposal"]["status"] == "pending_approval"


def test_vision_endpoint_rejects_invalid_image_without_cloud_fallback() -> None:
    with client() as test_client:
        response = test_client.post("/api/vision/analyze", json={
            "image_base64": "not valid base64!",
            "prompt": "Describe this image.",
        })
        assert response.status_code == 422
