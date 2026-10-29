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


def _approval_record(*, principal_id: str, approval_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        approval_id=approval_id,
        principal_id=principal_id,
        capability_id="test.capability",
        operation_id="read",
        resource_scope="/safe",
        status=SimpleNamespace(value="pending"),
        version=1,
        requested_at="2026-01-01T00:00:00+00:00",
        expires_at="2026-01-01T00:15:00+00:00",
    )


def _client(records: tuple[SimpleNamespace, ...]) -> TestClient:
    app = FastAPI()
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "principal-a"
    app.state.approval_store = SimpleNamespace(list_pending=lambda *, limit=100: records)
    app.include_router(approval_router)
    return TestClient(app)


def test_approval_queue_reads_pending_records_from_approval_store() -> None:
    client = _client(
        (
            _approval_record(principal_id="principal-a", approval_id="visible"),
            _approval_record(principal_id="principal-b", approval_id="another-principal"),
        )
    )

    response = client.get(
        "/api/approvals",
        headers={"Authorization": "Bearer " + "t" * 40},
    )

    assert response.status_code == 200
    assert [item["approval_id"] for item in response.json()] == ["visible", "another-principal"]
    assert all(item["status"] == "pending" for item in response.json())


def test_approval_projection_still_requires_bearer_authentication() -> None:
    response = _client(
        (_audit_record(principal_id="principal-a", request_id="visible"),)
    ).get("/api/approvals")

    assert response.status_code == 401
