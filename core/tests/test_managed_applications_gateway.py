"""Real child process and one-shot Owner approval integration, no mock process."""
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aura_core.enterprise.approval_store import ApprovalStatus, SQLiteApprovalStore
from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.events import EventBus
from aura_core.kernel.permissions import AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy
from aura_core.kernel.services import ServiceRegistry
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.provider import ProviderRegistry
from aura_core.providers.managed_applications_mcp import (
    GovernedManagedApplications, ManagedAppDenied, ManagedAppUnavailable,
    ManagedApplicationSpec, load_managed_app_manifest, register_managed_applications,
    managed_applications_router,
)

READ = "applications.managed.read"
START = "applications.managed.start"
STOP = "applications.managed.stop"


def run(coro):
    return asyncio.run(coro)


def make_spec(tmp_path: Path) -> ManagedApplicationSpec:
    script = tmp_path / "local_managed_example.py"
    script.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    exe = Path(sys.executable).resolve(strict=True)
    return ManagedApplicationSpec(
        app_id="sample", executable=str(exe),
        sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),
        arguments=("-u", str(script)),
    )


@pytest.fixture
def system(tmp_path):
    bus = EventBus()
    services = ServiceRegistry()
    providers = ProviderRegistry(services)
    caps = CapabilityRegistry(services)
    backend = register_managed_applications(
        services=services, providers=providers, capabilities=caps,
        specifications=(make_spec(tmp_path),), event_bus=bus,
    )
    engine = PermissionEngine(caps)
    with SQLiteApprovalStore(str(tmp_path / "approvals.sqlite3")) as approvals:
        gateway = MCPGateway(
            caps, providers, engine, approval_store=approvals,
            approval_fingerprint_key=b"x" * 32, event_bus=bus,
        )
        owner = GovernedManagedApplications(gateway, authenticated_principal_id="owner")
        yield bus, backend, engine, approvals, owner, providers, caps
    backend.close()


def policy(engine, cap, decision=AuthorizationDecision.REQUIRE_APPROVAL, principal="owner"):
    scope = ("applications/managed/read-only" if cap == READ
             else "applications/managed/sample/lifecycle")
    engine.add_policy(PermissionPolicy(
        policy_id=f"{principal}.{cap}.{decision.value}", policy_version="1.0.0",
        principal_id=principal, capability_id=cap, operation_id=cap,
        resource_scope=scope,
        authorization_level=(AuthorizationLevel.READ if cap == READ else
                             AuthorizationLevel.EXECUTE if decision is AuthorizationDecision.ALLOW else
                             AuthorizationLevel.USER_APPROVAL_REQUIRED),
        decision=decision,
    ))


def approve(store, pending):
    record = store.get(pending.approval_id)
    assert record is not None and record.status is ApprovalStatus.PENDING
    store.decide(record.approval_id, expected_version=record.version,
                 approver_id="human:owner", decision=ApprovalStatus.APPROVED)


def test_real_process_launch_status_stop_and_replay_denial(system):
    bus, backend, engine, approvals, owner, providers, caps = system
    policy(engine, START)
    policy(engine, STOP)
    policy(engine, READ, AuthorizationDecision.ALLOW)
    pending = run(owner.start("sample"))
    assert pending.state == "approval_required" and backend._owned == {}
    approve(approvals, pending)
    running = run(owner.start("sample", approval_id=pending.approval_id))
    assert running.state == "running"
    child = backend._owned[("owner", "sample")]
    assert child.poll() is None
    assert approvals.get(pending.approval_id).status is ApprovalStatus.CONSUMED
    assert run(owner.read()) == (running,)
    assert providers.resolve("applications.managed.local") is backend
    assert len(caps.records()) == 3
    with pytest.raises(ManagedAppDenied):
        run(owner.start("sample", approval_id=pending.approval_id))
    assert child.poll() is None
    stopping = run(owner.stop("sample"))
    assert stopping.state == "approval_required"
    approve(approvals, stopping)
    assert run(owner.stop("sample", approval_id=stopping.approval_id)).state == "stopped"
    assert child.poll() is not None and run(owner.read()) == ()
    assert approvals.get(stopping.approval_id).status is ApprovalStatus.CONSUMED
    events = []
    bus.subscribe("ManagedApplicationStateChanged", lambda event: events.append(event))
    for _ in range(32):
        run(bus.dispatch_once())
        if len(events) >= 2:
            break
    assert {ev.payload["state"] for ev in events} == {"running", "stopped"}
    assert all(ev.source_component == "aura.managed_applications" for ev in events)


@pytest.mark.parametrize("decision", [
    None, AuthorizationDecision.DENY, AuthorizationDecision.REQUIRE_APPROVAL,
])
def test_default_denial_or_pending_approval_does_not_launch(system, decision):
    _, backend, engine, approvals, owner, _, _ = system
    if decision is not None:
        policy(engine, START, decision)
    if decision is AuthorizationDecision.REQUIRE_APPROVAL:
        pending = run(owner.start("sample"))
        assert pending.state == "approval_required"
        assert approvals.get(pending.approval_id).status is ApprovalStatus.PENDING
    else:
        with pytest.raises(ManagedAppDenied):
            run(owner.start("sample"))
    assert backend._owned == {}


def test_unconditional_allow_cannot_bypass_consumed_high_risk_approval(system):
    _, backend, engine, _, owner, _, _ = system
    policy(engine, START, AuthorizationDecision.ALLOW)
    with pytest.raises(ManagedAppUnavailable):
        run(owner.start("sample"))
    assert backend._owned == {}


def test_direct_provider_cannot_execute_and_caller_cannot_override_argv(system):
    _, backend, engine, _, owner, _, _ = system
    policy(engine, START)
    with pytest.raises(ManagedAppDenied):
        run(backend.call_tool("start_managed_application", {"app_id": "sample"}))
    with pytest.raises(TypeError):
        run(owner.start("sample", arguments=["/bin/sh"]))
    with pytest.raises(ValueError):
        run(owner.start("sample; rm -rf x"))
    assert backend._owned == {}


def test_other_principal_cannot_read_or_stop_owner_process(system):
    _, backend, engine, approvals, owner, providers, caps = system
    policy(engine, START)
    pending = run(owner.start("sample"))
    approve(approvals, pending)
    run(owner.start("sample", approval_id=pending.approval_id))
    stranger = GovernedManagedApplications(
        MCPGateway(caps, providers, engine, approval_store=approvals,
                   approval_fingerprint_key=b"x" * 32),
        authenticated_principal_id="stranger",
    )
    with pytest.raises(ManagedAppDenied):
        run(stranger.read())
    with pytest.raises(ManagedAppDenied):
        run(stranger.stop("sample"))
    assert backend._owned[("owner", "sample")].poll() is None


def test_no_arbitrary_process_stop_even_with_approved_gateway(system):
    _, backend, engine, approvals, owner, _, _ = system
    policy(engine, STOP)
    pending = run(owner.stop("sample"))
    approve(approvals, pending)
    with pytest.raises(ManagedAppUnavailable):
        run(owner.stop("sample", approval_id=pending.approval_id))
    assert backend._owned == {}


def test_digest_rejection_and_operator_manifest_mode(tmp_path):
    exe = str(Path(sys.executable).resolve())
    with pytest.raises(ValueError, match="integrity"):
        ManagedApplicationSpec("sample", exe, "0" * 64)
    spec = make_spec(tmp_path)
    manifest = tmp_path / "managed-apps.json"
    manifest.write_text(json.dumps({"schema": "aura.managed-apps.v1",
        "applications": [{"app_id": spec.app_id, "executable": spec.executable,
                          "sha256": spec.sha256, "arguments": list(spec.arguments)}]}),
        encoding="utf-8")
    manifest.chmod(0o600)
    if os.name == "posix":
        assert load_managed_app_manifest(str(manifest)) == (spec,)
        manifest.chmod(0o666)
        with pytest.raises(ValueError):
            load_managed_app_manifest(str(manifest))
    else:
        with pytest.raises(ManagedAppUnavailable):
            load_managed_app_manifest(str(manifest))


def test_registration_is_explicit_and_duplicate_rejected(system):
    bus, backend, _, _, _, providers, caps = system
    with pytest.raises(ValueError):
        register_managed_applications(
            services=providers._service_registry, providers=providers,
            capabilities=caps, event_bus=bus,
            specifications=tuple(backend._specs.values()),
        )


def _api(owner=None, principal="owner"):
    app = FastAPI()
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = principal
    app.state.managed_applications = owner
    app.include_router(managed_applications_router)
    return app


def _auth():
    return {"Authorization": "Bearer " + "t" * 40}


def test_real_http_bearer_plus_gateway_approval_controls_start_stop(system):
    _, backend, engine, approvals, owner, _, _ = system
    policy(engine, READ, AuthorizationDecision.ALLOW)
    policy(engine, START)
    policy(engine, STOP)
    with TestClient(_api(owner)) as client:
        assert client.get("/api/runtime/managed-apps").status_code == 401
        assert client.get("/api/runtime/managed-apps", headers=_auth()).status_code == 200
        assert client.post("/api/runtime/managed-apps/sample/start",
                           headers=_auth(), json={"executable": "/bin/sh"}).status_code == 422
        pending = client.post("/api/runtime/managed-apps/sample/start",
                              headers=_auth(), json={})
        assert pending.status_code == 202 and pending.json()["state"] == "approval_required"
        assert backend._owned == {}
        approval = approvals.get(pending.json()["approval_id"])
        approvals.decide(approval.approval_id, expected_version=approval.version,
                         approver_id="human:owner", decision=ApprovalStatus.APPROVED)
        started = client.post("/api/runtime/managed-apps/sample/start", headers=_auth(),
                              json={"approval_id": approval.approval_id})
        assert started.status_code == 200 and started.json()["state"] == "running"
        assert client.get("/api/runtime/managed-apps", headers=_auth()).json()["applications"][0]["state"] == "running"
        stopped = client.post("/api/runtime/managed-apps/sample/stop", headers=_auth(), json={})
        assert stopped.status_code == 202
        r = approvals.get(stopped.json()["approval_id"])
        approvals.decide(r.approval_id, expected_version=r.version,
                         approver_id="human:owner", decision=ApprovalStatus.APPROVED)
        done = client.post("/api/runtime/managed-apps/sample/stop", headers=_auth(),
                           json={"approval_id": r.approval_id})
        assert done.status_code == 200 and done.json()["state"] == "stopped"
        assert "no-store" in done.headers["cache-control"]
        assert "script-src 'none'" in done.headers["content-security-policy"]


def test_http_disabled_or_wrong_principal_fails_closed(system):
    _, _, engine, _, owner, _, _ = system
    policy(engine, READ, AuthorizationDecision.ALLOW)
    with TestClient(_api(owner, principal="intruder")) as client:
        assert client.get("/api/runtime/managed-apps", headers=_auth()).status_code == 403
    with TestClient(_api(None)) as client:
        assert client.get("/api/runtime/managed-apps", headers=_auth()).status_code == 503


def test_http_bearer_is_not_a_gateway_policy_grant(system):
    _, _, _, _, owner, _, _ = system
    with TestClient(_api(owner)) as client:
        assert client.get("/api/runtime/managed-apps", headers=_auth()).status_code == 403
