"""Real Core PermissionEngine/CapabilityRegistry/SQLite approval boundary tests (#100)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aura_core.application.approval_api import router as approval_router
from aura_core.enterprise.approval_store import ApprovalStatus, SQLiteApprovalStore
from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType,
)
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy,
)
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry

_AUTH = {"Authorization": "Bearer " + "t" * 40}
_BODY = {"decision": "approved", "expected_version": 1}


def _store() -> SQLiteApprovalStore:
    store = SQLiteApprovalStore(":memory:")
    for identity in ("approval-one", "approval-two"):
        store.create(
            principal_id="requester", capability_id="test.write", operation_id="write",
            resource_scope="local", request_fingerprint="a" * 64,
            policy_digest="b" * 64, approval_id=identity,
        )
    return store


def _permission_engine() -> PermissionEngine:
    services = ServiceRegistry()
    service = services.register(
        ServiceDefinition(
            name="approval review", version="1.0.0", provider="aura",
            category=ServiceCategory.CORE,
        ),
        object(),
    )
    capabilities = CapabilityRegistry(services)
    capabilities.register(
        CapabilityDefinition(
            capability_id="approval.review", name="Approval Review",
            version="1.0.0", description="Guard cross-principal approval review",
            provider_id=service.service_id,
            provider_type=ProviderType.SERVICE,
            category=CapabilityCategory.SECURITY, risk_level="high",
        )
    )
    return PermissionEngine(capabilities)


def _allow(engine: PermissionEngine, operation: str, *,
           approval_id: str = "approval-one",
           principal_id: str = "reviewer",
           decision: AuthorizationDecision = AuthorizationDecision.ALLOW) -> None:
    engine.add_policy(PermissionPolicy(
        policy_id=f"{principal_id}.{operation}.{approval_id}",
        policy_version="1.0.0",
        principal_id=principal_id,
        capability_id="approval.review",
        operation_id=operation,
        resource_scope=f"approval/requester/{approval_id}",
        authorization_level=AuthorizationLevel.PRIVILEGED,
        decision=decision,
    ))


def _client(store: SQLiteApprovalStore, principal: str, engine=None) -> TestClient:
    app = FastAPI()
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = principal
    app.state.approval_store = store
    if engine is not None:
        app.state.permission_engine = engine
    app.include_router(approval_router)
    return TestClient(app)


def test_missing_review_policy_hides_other_principals_and_blocks_decision():
    with _store() as store:
        client = _client(store, "reviewer")
        assert client.get("/api/approvals", headers=_AUTH).json() == []
        response = client.post("/api/approvals/approval-one/decision", headers=_AUTH, json=_BODY)
        assert response.status_code == 403
        assert store.get("approval-one").status is ApprovalStatus.PENDING


def test_explicit_registry_and_permission_engine_allow_exact_scope():
    with _store() as store:
        engine = _permission_engine()
        _allow(engine, "approval.list")
        _allow(engine, "approval.decide")
        client = _client(store, "reviewer", engine)
        assert [r["approval_id"] for r in client.get("/api/approvals", headers=_AUTH).json()] == ["approval-one"]
        response = client.post("/api/approvals/approval-one/decision", headers=_AUTH, json=_BODY)
        assert response.status_code == 200
        assert response.json()["status"] == "approved"
        assert store.get("approval-one").approver_id == "reviewer"
        assert store.get("approval-two").status is ApprovalStatus.PENDING
        assert len(engine.audit_records()) >= 2


def test_list_permission_is_not_a_decision_permission():
    with _store() as store:
        engine = _permission_engine()
        _allow(engine, "approval.list")
        client = _client(store, "reviewer", engine)
        assert client.get("/api/approvals", headers=_AUTH).status_code == 200
        response = client.post("/api/approvals/approval-one/decision", headers=_AUTH, json=_BODY)
        assert response.status_code == 403
        assert store.get("approval-one").status is ApprovalStatus.PENDING


def test_deferred_or_explicit_approval_policy_is_not_an_allow():
    with _store() as store:
        engine = _permission_engine()
        _allow(engine, "approval.decide", decision=AuthorizationDecision.REQUIRE_APPROVAL)
        client = _client(store, "reviewer", engine)
        assert client.post("/api/approvals/approval-one/decision", headers=_AUTH, json=_BODY).status_code == 403
        assert store.get("approval-one").status is ApprovalStatus.PENDING


def test_requester_cannot_self_approve_even_with_high_privilege_policy():
    with _store() as store:
        engine = _permission_engine()
        _allow(engine, "approval.decide", principal_id="requester")
        client = _client(store, "requester", engine)
        assert client.post("/api/approvals/approval-one/decision", headers=_AUTH, json=_BODY).status_code == 403
        assert store.get("approval-one").status is ApprovalStatus.PENDING


def test_another_approval_id_does_not_inherit_scope_or_forged_principal_header():
    with _store() as store:
        engine = _permission_engine()
        _allow(engine, "approval.decide")
        client = _client(store, "reviewer", engine)
        result = client.post("/api/approvals/approval-two/decision", headers={
            **_AUTH, "X-Principal-ID": "requester",
        }, json=_BODY)
        assert result.status_code == 403
        assert store.get("approval-two").status is ApprovalStatus.PENDING
        assert client.post("/api/approvals/approval-one/decision", json=_BODY).status_code == 401
