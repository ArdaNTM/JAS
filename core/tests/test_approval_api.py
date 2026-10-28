from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from aura_core.application.approval_api import router as approval_router
from aura_core.kernel.permissions import AuthorizationDecision


def _audit_record(*, principal_id: str, request_id: str) -> SimpleNamespace:
    now = datetime.now(UTC)
    request = SimpleNamespace(
        request_id=request_id,
        principal_id=principal_id,
        task_id=f"task-{request_id}",
        capability_id="test.capability",
        operation_id="read",
        resource_scope="/safe",
        risk_level="high",
    )
    decision = SimpleNamespace(
        decision=AuthorizationDecision.REQUIRE_APPROVAL,
        reason="approval required",
        timestamp=now,
    )
    return SimpleNamespace(request=request, decision=decision)


def _client(records: tuple[SimpleNamespace, ...]) -> TestClient:
    app = FastAPI()
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "principal-a"
    app.state.permission_engine = SimpleNamespace(
        audit_records=lambda: records,
    )
    app.include_router(approval_router)
    return TestClient(app)


def test_approval_projection_only_returns_authenticated_principals_records() -> None:
    client = _client(
        (
            _audit_record(principal_id="principal-a", request_id="visible"),
            _audit_record(principal_id="principal-b", request_id="secret"),
        )
    )

    response = client.get(
        "/api/approvals",
        headers={"Authorization": "Bearer " + "t" * 40},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["visible"]
    assert all(item["principal_id"] == "principal-a" for item in response.json())


def test_approval_projection_still_requires_bearer_authentication() -> None:
    response = _client(
        (_audit_record(principal_id="principal-a", request_id="visible"),)
    ).get("/api/approvals")

    assert response.status_code == 401
