"""Real local process lifecycle, consumed approvals and negative safety boundary."""
import asyncio
import hashlib
import sys
from pathlib import Path

import pytest

from aura_core.enterprise.approval_store import ApprovalStatus, SQLiteApprovalStore
from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.events import EventBus
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy,
)
from aura_core.kernel.services import ServiceRegistry
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.provider import ProviderRegistry
from aura_core.providers.governed_app_supervisor import (
    ApplicationDenied, ApplicationUnavailable, GovernedApplications,
    TrustedApplication, register_governed_app_supervisor,
)

_APP_PATH = Path(sys.executable).resolve()


def _trusted(*, sha=None):
    return TrustedApplication(
        app_id="owner.test.app", executable=str(_APP_PATH),
        sha256=sha or hashlib.sha256(_APP_PATH.read_bytes()).hexdigest(),
        argv=("-c", "import time; time.sleep(30)"),
    )


def _system(tmp_path, *, read=True, actions=AuthorizationDecision.REQUIRE_APPROVAL,
            profile=None, owner="owner"):
    bus = EventBus()
    services = ServiceRegistry()
    providers = ProviderRegistry(services)
    caps = CapabilityRegistry(services)
    backend = register_governed_app_supervisor(
        services=services, providers=providers, capabilities=caps,
        profiles=(profile or _trusted(),), event_bus=bus,
    )
    engine = PermissionEngine(caps)
    if read:
        engine.add_policy(PermissionPolicy(
            policy_id="owner.app.read", policy_version="1.0.0",
            principal_id="owner", capability_id="application.instances.read",
            operation_id="application.instances.read",
            resource_scope="application/owned-instances/read-only",
            authorization_level=AuthorizationLevel.READ,
            decision=AuthorizationDecision.ALLOW,
        ))
    if actions is not None:
        for cap, scope in (
            ("application.launch", "application/trusted-catalog/launch"),
            ("application.stop", "application/owned-instances/stop"),
        ):
            engine.add_policy(PermissionPolicy(
                policy_id="owner.app." + cap, policy_version="1.0.0",
                principal_id="owner", capability_id=cap, operation_id=cap,
                resource_scope=scope, authorization_level=AuthorizationLevel.EXECUTE,
                decision=actions,
            ))
    store = SQLiteApprovalStore(str(tmp_path / "approvals.db"))
    gateway = MCPGateway(caps, providers, engine, approval_store=store,
                         approval_fingerprint_key=b"a" * 32, event_bus=bus)
    user = GovernedApplications(gateway, authenticated_principal_id=owner)
    return user, backend, store, engine, bus, providers, caps


def _run(op):
    return asyncio.run(op)


def _approve(store, pending):
    assert pending.approval_required and pending.instance is None
    record = store.get(pending.approval_id)
    assert record.status is ApprovalStatus.PENDING
    approved = store.decide(
        pending.approval_id, expected_version=record.version,
        approver_id="human:owner", decision=ApprovalStatus.APPROVED,
    )
    assert approved.status is ApprovalStatus.APPROVED
    return pending.approval_id


def test_real_process_is_not_started_until_approval_consumed(tmp_path):
    user, backend, store, engine, bus, providers, caps = _system(tmp_path)
    try:
        assert _run(user.list_owned()) == ()
        requested = _run(user.launch("owner.test.app"))
        assert requested.approval_required
        assert not backend._handles
        receipt = _approve(store, requested)
        started = _run(user.launch("owner.test.app", approval_id=receipt))
        assert started.instance is not None
        assert started.instance.state == "running"
        assert not started.approval_required
        assert store.get(receipt).status is ApprovalStatus.CONSUMED
        visible = _run(user.list_owned())
        assert len(visible) == 1
        assert visible[0].app_id == "owner.test.app"
        assert visible[0].instance_id == started.instance.instance_id
        assert caps.resolve("application.launch").definition.tool_name == "launch_trusted_app"
        assert providers.resolve("application.supervisor.local") is backend
        assert any(a.decision.decision is AuthorizationDecision.REQUIRE_APPROVAL
                   for a in engine.audit_records())
        # A consumed approval must never be usable twice.
        with pytest.raises(ApplicationDenied):
            _run(user.launch("owner.test.app", approval_id=receipt))
        assert len(_run(user.list_owned())) == 1
        stop_pending = _run(user.stop(started.instance.instance_id))
        assert stop_pending.approval_required
        assert len(_run(user.list_owned())) == 1
        stop_receipt = _approve(store, stop_pending)
        stopped = _run(user.stop(started.instance.instance_id, approval_id=stop_receipt))
        assert stopped.instance.state == "stopped"
        assert _run(user.list_owned()) == ()
        assert backend._handles == {}
        # Real Kernel EventBus receives redacted start and stop notifications.
        types = []
        bus.subscribe("ApplicationStarted", lambda event: types.append(event.event_type))
        bus.subscribe("ApplicationStopped", lambda event: types.append(event.event_type))
        # Gateway telemetry events without subscribers can dead-letter; drain
        # the real queue until both authorized lifecycle notifications arrive.
        for _ in range(32):
            _run(bus.dispatch_once())
            if len(types) >= 2:
                break
        assert "ApplicationStarted" in types
        assert "ApplicationStopped" in types
    finally:
        backend.close()
        store.close()


@pytest.mark.parametrize("action_decision", [None, AuthorizationDecision.DENY])
def test_without_explicit_action_policy_no_process_is_launched(tmp_path, action_decision):
    user, backend, store, *_ = _system(tmp_path, actions=action_decision)
    try:
        with pytest.raises(ApplicationDenied):
            _run(user.launch("owner.test.app"))
        assert backend._handles == {}
    finally:
        backend.close()
        store.close()


def test_even_an_accidental_allow_policy_cannot_launch_or_stop_without_approval(tmp_path):
    user, backend, store, *_ = _system(tmp_path, actions=AuthorizationDecision.ALLOW)
    try:
        with pytest.raises(ApplicationUnavailable):
            _run(user.launch("owner.test.app"))
        assert backend._handles == {}
        with pytest.raises(ApplicationDenied):
            _run(backend.call_tool("launch_trusted_app", {"app_id": "owner.test.app"}))
    finally:
        backend.close()
        store.close()


def test_direct_provider_call_cannot_bypass_mcp_dispatch(tmp_path):
    user, backend, store, *_ = _system(tmp_path)
    try:
        for name, data in (
            ("list_owned_apps", {}),
            ("launch_trusted_app", {"app_id": "owner.test.app"}),
            ("stop_owned_app", {"instance_id": "untrusted"}),
        ):
            with pytest.raises(ApplicationDenied):
                _run(backend.call_tool(name, data))
        assert backend._handles == {}
    finally:
        backend.close()
        store.close()


def test_bad_executable_digest_rejected_after_approval_no_process(tmp_path):
    profile = _trusted(sha="0" * 64)
    user, backend, store, *_ = _system(tmp_path, profile=profile)
    try:
        receipt = _approve(store, _run(user.launch("owner.test.app")))
        with pytest.raises(ApplicationUnavailable):
            _run(user.launch("owner.test.app", approval_id=receipt))
        assert backend._handles == {}
    finally:
        backend.close()
        store.close()


def test_unregistered_catalog_and_user_controlled_args_rejected(tmp_path):
    user, backend, store, *_ = _system(tmp_path)
    try:
        receipt = _approve(store, _run(user.launch("not.registered")))
        with pytest.raises(ApplicationUnavailable):
            _run(user.launch("not.registered", approval_id=receipt))
        with pytest.raises(TypeError):
            _run(user.launch("owner.test.app", argv=("-c", "rm -rf /")))
        assert backend._handles == {}
    finally:
        backend.close()
        store.close()


def test_principal_isolation_even_with_approved_foreign_owner(tmp_path):
    user, backend, store, engine, bus, providers, caps = _system(tmp_path)
    try:
        receipt = _approve(store, _run(user.launch("owner.test.app")))
        started = _run(user.launch("owner.test.app", approval_id=receipt))
        engine.add_policy(PermissionPolicy(
            policy_id="other.read", policy_version="1.0.0", principal_id="other",
            capability_id="application.instances.read",
            operation_id="application.instances.read",
            resource_scope="application/owned-instances/read-only",
            authorization_level=AuthorizationLevel.READ,
            decision=AuthorizationDecision.ALLOW,
        ))
        other = GovernedApplications(
            MCPGateway(caps, providers, engine, approval_store=store,
                       approval_fingerprint_key=b"a"*32), authenticated_principal_id="other",
        )
        assert _run(other.list_owned()) == ()
        # Other caller has no stop policy; cannot terminate our process.
        with pytest.raises(ApplicationDenied):
            _run(other.stop(started.instance.instance_id))
        assert len(_run(user.list_owned())) == 1
    finally:
        backend.close()
        store.close()


def test_trusted_profile_input_validation_and_no_symlink_alias(tmp_path):
    with pytest.raises(ValueError):
        TrustedApplication("id", "python", "0"*64)
    with pytest.raises(ValueError):
        TrustedApplication("id", str(_APP_PATH), "0"*63)
    with pytest.raises(ValueError):
        TrustedApplication("id", str(_APP_PATH), "0"*64, argv=["a"])
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(_APP_PATH)
    except (OSError, NotImplementedError):
        pytest.skip("Host does not permit symlink creation")
    with pytest.raises(ValueError):
        TrustedApplication(
            "test", str(alias), hashlib.sha256(_APP_PATH.read_bytes()).hexdigest()
        ).verify_executable()


def test_catalog_size_duplicate_and_direct_query_paths_guarded(tmp_path):
    p = _trusted()
    user, backend, store, _, bus, providers, caps = _system(tmp_path)
    try:
        with pytest.raises(ValueError):
            register_governed_app_supervisor(
                services=providers._service_registry, providers=providers,
                capabilities=caps, profiles=(p,), event_bus=bus,
            )
        with pytest.raises(ValueError):
            type(backend)((p,p),bus)
        assert "subprocess.Popen" not in repr(_run(user.list_owned()))
    finally:
        backend.close()
        store.close()
