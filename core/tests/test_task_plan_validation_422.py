"""Task planner input failures are HTTP 422, never unhandled HTTP 500."""
from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from aura_core.application.api import create_api
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig


class Transport:
    def post_json(self, endpoint, payload, timeout):
        return {"model": "test", "message": {"content": "ok"}, "done": True}

    def get_json(self, endpoint, timeout):
        return {"models": []}


def test_task_plan_value_error_is_structured_422_and_preserves_auth(monkeypatch):
    monkeypatch.setenv("AURA_ASSISTANT_AUTO_TOOLS_ENABLED", "0")
    app = create_api(
        RuntimeConfig(model="test"),
        BackendConfig(endpoint="http://127.0.0.1:11434", timeout=1),
        Transport(),
    )
    app.state.http_bearer_token = "z" * 40
    app.state.http_principal_id = "local_owner"

    def reject(_directive):
        raise ValueError("Invalid or unsupported task directive")

    app.state.directive_planner = SimpleNamespace(plan=reject)
    with TestClient(app) as client:
        response = client.post(
            "/api/tasks/plan",
            json={"directive": "Run unsafe action"},
            headers={"Authorization": "Bearer " + "z" * 40},
        )
        assert response.status_code == 422
        assert response.json() == {
            "detail": {
                "code": "INVALID_TASK_DIRECTIVE",
                "message": "Invalid or unsupported task directive",
            }
        }
        denied = client.post(
            "/api/tasks/plan", json={"directive": "Run unsafe action"},
        )
        assert denied.status_code in (401, 403)
