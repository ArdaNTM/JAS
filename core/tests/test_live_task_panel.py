"""Real SQLite and EventBus task projection through MCPGateway and HTTP."""
import asyncio
from dataclasses import FrozenInstanceError

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aura_core.application.live_task_panel import (
    GovernedLiveTaskPanel, LiveTaskDenied, LiveTaskUnavailable,
    live_task_panel_router, register_live_task_panel,
)
from aura_core.application.task_state_machine import TaskState, TaskStateMachine
from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy,
)
from aura_core.kernel.services import ServiceRegistry
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.provider import ProviderRegistry


def system(*, decision=None, principal="owner"):
    bus = EventBus()
    store = TaskStateMachine(":memory:", event_bus=bus)
    services = ServiceRegistry()
    providers = ProviderRegistry(services)
    caps = CapabilityRegistry(services)
    backend = register_live_task_panel(
        services=services, providers=providers, capabilities=caps,
        event_bus=bus, task_state_machine=store,
    )
    engine = PermissionEngine(caps)
    if decision is not None:
        engine.add_policy(PermissionPolicy(
            policy_id="owner.tasks.panel", policy_version="1.0.0",
            principal_id="owner", capability_id="visualization.tasks.read",
            operation_id="visualization.tasks.read",
            resource_scope="visualization/tasks/read-only",
            authorization_level=AuthorizationLevel.READ, decision=decision,
        ))
    reader = GovernedLiveTaskPanel(
        MCPGateway(caps, providers, engine), authenticated_principal_id=principal,
    )
    return bus, store, backend, reader, engine, providers, caps


def read(reader):
    return asyncio.run(reader.read())


def test_real_persisted_lifecycle_is_owner_scoped_and_redacted():
    bus, store, backend, reader, engine, providers, caps = system(
        decision=AuthorizationDecision.ALLOW,
    )
    first = store.create_task(principal_id="owner", goal="PRIVATE_GOAL_SECRET")
    store.create_task(principal_id="other", goal="FOREIGN_SECRET")
    store.transition(first.task_id, principal_id="owner", target=TaskState.RUNNING)
    store.transition(first.task_id, principal_id="owner", target=TaskState.SUCCEEDED)
    assert asyncio.run(bus.dispatch_once()) is True
    assert backend._seen_changes == 1
    evidence = read(reader)
    assert evidence.read_only and evidence.trust == "SCOPED_PERSISTED_TASK_STATE"
    assert len(evidence.tasks) == 1
    assert evidence.tasks[0].task_id == first.task_id
    assert evidence.tasks[0].state == "succeeded"
    assert evidence.tasks[0].revision == 2
    assert "SECRET" not in repr(evidence)
    assert providers.resolve("visualization.tasks.local") is backend
    assert caps.resolve("visualization.tasks.read").definition.tool_name == "read_live_task_states"
    assert engine.audit_records()[-1].decision.decision is AuthorizationDecision.ALLOW
    with pytest.raises(FrozenInstanceError):
        evidence.tasks[0].state = "running"
    backend.close()
    store.close()


def test_owner_scoped_sql_limit_applies_before_materialization():
    _, store, _, reader, _, _, _ = system(decision=AuthorizationDecision.ALLOW)
    for i in range(80):
        store.create_task(principal_id="owner", goal="task", task_id=f"task-{i:03d}")
    store.create_task(principal_id="other", goal="foreign", task_id="other-01")
    result = read(reader)
    assert len(result.tasks) == 64
    assert "task-079" in {r.task_id for r in result.tasks}
    assert all(r.task_id != "other-01" for r in result.tasks)
    with pytest.raises(ValueError):
        store.list_tasks_limited(principal_id="owner", limit=65)
    with pytest.raises(ValueError):
        store.list_tasks_limited(principal_id="owner", limit=True)
    store.close()


@pytest.mark.parametrize("decision", [
    None, AuthorizationDecision.DENY, AuthorizationDecision.REQUIRE_APPROVAL,
])
def test_absent_deny_or_pending_approval_never_reads_tasks(decision):
    _, store, _, reader, engine, _, _ = system(decision=decision)
    store.create_task(principal_id="owner", goal="secret")
    with pytest.raises(LiveTaskDenied):
        read(reader)
    assert engine.audit_records()[-1].decision.decision is not AuthorizationDecision.ALLOW
    store.close()


def test_direct_provider_cannot_bypass_gateway_and_registration_is_opt_in():
    _, store, backend, reader, engine, providers, caps = system()
    with pytest.raises(LiveTaskDenied):
        asyncio.run(backend.call_tool("read_live_task_states", {}))
    with pytest.raises(LiveTaskDenied):
        read(reader)
    with pytest.raises(ValueError):
        register_live_task_panel(
            services=providers._service_registry, providers=providers,
            capabilities=caps, event_bus=EventBus(), task_state_machine=store,
        )
    store.close()


def test_other_principal_cannot_use_owner_grant():
    _, store, _, _, engine, providers, caps = system(
        decision=AuthorizationDecision.ALLOW,
    )
    store.create_task(principal_id="owner", goal="secret")
    other = GovernedLiveTaskPanel(
        MCPGateway(caps, providers, engine), authenticated_principal_id="other",
    )
    with pytest.raises(LiveTaskDenied):
        read(other)
    store.close()


def test_forged_event_changes_no_persisted_state():
    bus, store, _, reader, _, _, _ = system(
        decision=AuthorizationDecision.ALLOW,
    )
    record = store.create_task(principal_id="owner", goal="private")
    bus.publish(KernelEvent(event_type="TaskStateChanged",
        source_component="aura.task_state_machine",
        payload={"task_id": record.task_id, "state": "succeeded",
                 "principal_id": "owner", "goal": "FORGED_SECRET"}))
    for _ in range(3):
        asyncio.run(bus.dispatch_once())
    assert read(reader).tasks[0].state == "ready"
    assert "FORGED_SECRET" not in repr(read(reader))
    store.close()


def test_forged_provider_row_and_secret_exception_are_rejected():
    _, store, backend, reader, _, _, _ = system(
        decision=AuthorizationDecision.ALLOW,
    )
    async def malicious(name, arguments):
        return {"trust": "SCOPED_PERSISTED_TASK_STATE", "tasks": [{
            "task_id": "<script>", "state": "running", "revision": 0,
            "updated_at": "2026-11-18T00:00:00+00:00", "principal_id": "owner",
        }]}
    backend.call_tool = malicious
    with pytest.raises(LiveTaskUnavailable):
        read(reader)
    async def leak(name, arguments):
        raise RuntimeError("BEARER_SECRET")
    backend.call_tool = leak
    with pytest.raises(LiveTaskUnavailable) as err:
        read(reader)
    assert "SECRET" not in str(err.value)
    store.close()


def app(reader=None, *, principal="owner"):
    web = FastAPI()
    web.state.http_bearer_token = "t" * 40
    web.state.http_principal_id = principal
    web.state.live_task_panel = reader
    web.include_router(live_task_panel_router)
    return web


def auth():
    return {"Authorization": "Bearer " + "t" * 40}


def test_fastapi_bearer_and_gateway_both_required_and_json_redacted():
    _, store, _, reader, _, _, _ = system(
        decision=AuthorizationDecision.ALLOW,
    )
    store.create_task(principal_id="owner", goal="SECRET")
    with TestClient(app(reader)) as client:
        assert client.get("/api/runtime/tasks").status_code == 401
        response = client.get("/api/runtime/tasks", headers=auth())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["cache-control"] == "private, no-store"
    assert "script-src 'none'" in response.headers["content-security-policy"]
    assert response.json()["tasks"][0]["state"] == "ready"
    assert response.json()["read_only"] is True
    assert "SECRET" not in response.text
    store.close()


def test_http_denies_without_gateway_policy_and_wrong_principal():
    _, store, _, reader, engine, _, _ = system()
    with TestClient(app(reader)) as client:
        assert client.get("/api/runtime/tasks", headers=auth()).status_code == 403
    with TestClient(app(reader, principal="other")) as client:
        assert client.get("/api/runtime/tasks", headers=auth()).status_code == 403
    assert len(engine.audit_records()) == 1
    store.close()


def test_http_fails_closed_when_feature_disabled():
    with TestClient(app()) as client:
        assert client.get("/api/runtime/tasks", headers=auth()).status_code == 503
