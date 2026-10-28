from fastapi.testclient import TestClient

from aura_core.application.api import create_api
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig


class Transport:
    def post_json(self, endpoint, payload, timeout):
        return {"model": "test", "message": {"content": "ok"}, "done": True}

    def get_json(self, endpoint, timeout):
        return {"models": [{"name": "test"}]}


def _client() -> TestClient:
    app = create_api(
        RuntimeConfig(model="test"),
        BackendConfig(endpoint="http://test", timeout=1),
        Transport(),
    )
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "local_owner"
    return TestClient(app)


def test_reasoning_execute_rejects_missing_bearer_before_runtime_dispatch() -> None:
    response = _client().post(
        "/api/reasoning/execute",
        json={"directive": "search for public information about MCP", "confirmed": False},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_capability_approval_rejects_missing_bearer() -> None:
    response = _client().post(
        "/api/capabilities/proposals/proposal-1/approve",
        json={"confirmed": True},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_python_execution_rejects_missing_bearer() -> None:
    response = _client().post(
        "/api/autonomy/python",
        json={"source": "print(1)", "data": {}},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_reflexion_execution_rejects_missing_bearer() -> None:
    response = _client().post(
        "/api/autonomy/reflexion",
        json={"task_id": "test-task", "goal": "test", "source": "print(1)", "input_data": {}},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_authenticated_capability_approval_reaches_governed_handler() -> None:
    response = _client().post(
        "/api/capabilities/proposals/proposal-1/approve",
        json={"confirmed": True},
        headers={"Authorization": "Bearer " + "t" * 40},
    )
    # No proposal store is configured in this isolated test. Reaching the
    # handler's 404 confirms auth passed without performing any approval.
    assert response.status_code == 404
    assert response.json()["detail"] == "No capability proposals are pending"
