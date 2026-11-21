"""Stage C reports disabled state without granting dispatch authority."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from aura_core.application.stage_c_api import router


def test_disabled_stage_c_status_is_readable_but_runs_fail_closed():
    app = FastAPI()
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "local_owner"
    app.state.stage_c_controller = None
    app.include_router(router)
    client = TestClient(app)
    assert client.get("/api/stage-c/status").status_code == 401
    headers = {"Authorization": "Bearer " + "t" * 40}
    status = client.get("/api/stage-c/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["enabled"] is False
    result = client.post("/api/stage-c/runs", headers=headers,
                         json={"goal": "click", "confirmed": True})
    assert result.status_code == 503
