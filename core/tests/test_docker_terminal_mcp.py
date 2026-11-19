"""Real Docker subprocess entrypoint, Gateway approvals, and fail-closed tests."""
import asyncio
import hashlib
import json
import os
import shutil
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
from aura_core.providers.docker_terminal_mcp import (
    DockerSandboxEngine, TerminalCommand, GovernedDockerTerminal,
    TerminalDenied, TerminalUnavailable, register_docker_terminal,
    load_terminal_config, terminal_router,
)

IMAGE = "alpine@sha256:" + "a" * 64


def run(value):
    return asyncio.run(value)


def _setup(tmp_path, decision=None):
    bus = EventBus()
    services = ServiceRegistry()
    providers = ProviderRegistry(services)
    caps = CapabilityRegistry(services)
    cli = str(Path(sys.executable).resolve())
    engine = DockerSandboxEngine(docker_executable=cli, docker_sha256=hashlib.sha256(Path(cli).read_bytes()).hexdigest())
    backend = register_docker_terminal(services=services, providers=providers,
                                       capabilities=caps, event_bus=bus, engine=engine,
                                       commands=(TerminalCommand("inspect", IMAGE, ("pwd",)),))
    permissions = PermissionEngine(caps)
    if decision is not None:
        permissions.add_policy(PermissionPolicy(
            policy_id="terminal.owner.inspect", policy_version="1.0.0",
            principal_id="owner", capability_id="terminal.sandbox.execute",
            operation_id="terminal.sandbox.execute", resource_scope="terminal/sandbox/inspect",
            authorization_level=AuthorizationLevel.USER_APPROVAL_REQUIRED if decision is AuthorizationDecision.REQUIRE_APPROVAL else AuthorizationLevel.EXECUTE,
            decision=decision,
        ))
    approvals = SQLiteApprovalStore(str(tmp_path / "terminal-approvals.db"))
    gateway = MCPGateway(caps, providers, permissions, approval_store=approvals,
                         approval_fingerprint_key=b"z" * 32, event_bus=bus)
    return bus, backend, permissions, approvals, GovernedDockerTerminal(gateway, principal_id="owner")


def test_real_pinned_runtime_cli_is_invoked_only_after_consumed_approval(tmp_path):
    # sys.executable is a real OS binary but NOT Docker; the Popen execution
    # contract is exercised without claiming that this test proves isolation.
    bus, backend, engine, approvals, owner = _setup(tmp_path, AuthorizationDecision.REQUIRE_APPROVAL)
    try:
        pending = run(owner.run("inspect"))
        assert pending.status == "approval_required"
        assert approvals.get(pending.approval_id).status is ApprovalStatus.PENDING
        row = approvals.get(pending.approval_id)
        approvals.decide(row.approval_id, expected_version=row.version,
                         approver_id="human:owner", decision=ApprovalStatus.APPROVED)
        executed = run(owner.run("inspect", approval_id=pending.approval_id))
        assert executed.status == "executed" and executed.exit_code != 0
        assert "AURA_API_BEARER_TOKEN" not in executed.stdout
        assert approvals.get(pending.approval_id).status is ApprovalStatus.CONSUMED
        with pytest.raises(TerminalDenied):
            run(owner.run("inspect", approval_id=pending.approval_id))
    finally:
        approvals.close()


@pytest.mark.parametrize("decision", [None, AuthorizationDecision.DENY])
def test_no_policy_or_denied_never_dispatches(tmp_path, decision):
    _, _, engine, approvals, owner = _setup(tmp_path, decision)
    try:
        with pytest.raises(TerminalDenied):
            run(owner.run("inspect"))
        assert engine.audit_records()[-1].decision.decision is not AuthorizationDecision.ALLOW
    finally:
        approvals.close()


def test_unconsumed_approval_never_executes(tmp_path):
    _, _, engine, approvals, owner = _setup(tmp_path, AuthorizationDecision.REQUIRE_APPROVAL)
    try:
        result = run(owner.run("inspect"))
        assert result.status == "approval_required"
        assert approvals.get(result.approval_id).status is ApprovalStatus.PENDING
    finally:
        approvals.close()


def test_direct_provider_bypass_and_user_command_injection_denied(tmp_path):
    _, backend, _, approvals, owner = _setup(tmp_path, AuthorizationDecision.REQUIRE_APPROVAL)
    try:
        with pytest.raises(TerminalDenied):
            run(backend.call_tool("run_pinned_terminal_command", {"command_id": "inspect"}))
        with pytest.raises(TypeError):
            run(owner.run("inspect", argv=("sh",)))
        with pytest.raises(ValueError):
            run(owner.run("inspect;rm -rf /"))
        with pytest.raises(TerminalDenied):
            run(owner.run("other"))
    finally:
        approvals.close()


def test_no_unpinned_images_or_arbitrary_argv():
    with pytest.raises(ValueError):
        TerminalCommand("inspect", "alpine:latest", ("pwd",))
    with pytest.raises(ValueError):
        TerminalCommand("inspect", IMAGE, ("sh\x00",))
    with pytest.raises(ValueError):
        TerminalCommand("inspect", IMAGE, ("pwd",), timeout_seconds=999)
    with pytest.raises(ValueError):
        TerminalCommand("../../breakout", IMAGE, ("pwd",))


def test_tampered_host_cli_is_refused(tmp_path):
    cli = Path(sys.executable).resolve()
    with pytest.raises(ValueError):
        DockerSandboxEngine(docker_executable=str(cli), docker_sha256="0" * 64)


def test_real_docker_engine_offline_when_preloaded_and_allowed(tmp_path):
    """An optional live engine contract; absence is a documented acceptance gate."""
    image = os.environ.get("AURA_TEST_TERMINAL_PINNED_IMAGE", "")
    cli = shutil.which("docker")
    if not image or not cli:
        pytest.skip("No operator-preloaded pinned Docker image for a real isolation smoke")
    cli = str(Path(cli).resolve())
    if not image.startswith("alpine@sha256:"):
        pytest.skip("Live test requires a pinned Alpine image")
    engine = DockerSandboxEngine(
        docker_executable=cli, docker_sha256=hashlib.sha256(Path(cli).read_bytes()).hexdigest(),
    )
    output = engine.run(TerminalCommand("check", image, ("pwd",), timeout_seconds=15))
    assert output["exit_code"] == 0
    assert output["stdout"].strip() == "/workspace"
    assert output["trust"] == "UNTRUSTED_CONTAINER_OUTPUT"



def test_operator_manifest_has_private_mode_and_fixed_digest(tmp_path):
    cli = str(Path(sys.executable).resolve())
    manifest = tmp_path / "terminal.json"
    config = {"schema": "aura.terminal.docker.v1",
              "docker_executable": cli,
              "docker_sha256": hashlib.sha256(Path(cli).read_bytes()).hexdigest(),
              "commands": [{"command_id": "inspect", "image": IMAGE,
                            "argv": ["pwd"], "timeout_seconds": 10}]}
    manifest.write_text(json.dumps(config), encoding="utf-8")
    manifest.chmod(0o600)
    if os.name == "posix":
        engine, commands = load_terminal_config(str(manifest))
        assert engine.executable == cli and commands[0].command_id == "inspect"
        manifest.chmod(0o666)
        with pytest.raises(TerminalUnavailable):
            load_terminal_config(str(manifest))
    else:
        with pytest.raises(TerminalUnavailable):
            load_terminal_config(str(manifest))


def test_authenticated_http_never_infers_policy_or_accepts_arbitrary_shell(tmp_path):
    _, _, policy, approvals, owner = _setup(tmp_path, AuthorizationDecision.REQUIRE_APPROVAL)
    app = FastAPI()
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "owner"
    app.state.governed_terminal = owner
    app.include_router(terminal_router)
    headers = {"Authorization": "Bearer " + "t" * 40}
    try:
        with TestClient(app) as client:
            assert client.post("/api/runtime/terminal/inspect", json={}).status_code == 401
            assert client.post("/api/runtime/terminal/inspect", headers=headers,
                               json={"command": "rm -rf /"}).status_code == 422
            pending = client.post("/api/runtime/terminal/inspect", headers=headers, json={})
            assert pending.status_code == 202
            receipt = pending.json()["approval_id"]
            assert approvals.get(receipt).status is ApprovalStatus.PENDING
            entry = approvals.get(receipt)
            approvals.decide(receipt, expected_version=entry.version,
                             approver_id="human:owner", decision=ApprovalStatus.APPROVED)
            done = client.post("/api/runtime/terminal/inspect", headers=headers,
                               json={"approval_id": receipt})
            assert done.status_code == 200
            assert done.json()["trust"] == "UNTRUSTED_CONTAINER_OUTPUT"
            assert "no-store" in done.headers["cache-control"]
            assert client.post("/api/runtime/terminal/inspect", headers=headers,
                               json={"approval_id": receipt}).status_code == 403
    finally:
        approvals.close()


def test_http_disabled_and_wrong_principal_fail_closed(tmp_path):
    _, _, engine, approvals, owner = _setup(tmp_path, AuthorizationDecision.REQUIRE_APPROVAL)
    app = FastAPI()
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "different"
    app.state.governed_terminal = owner
    app.include_router(terminal_router)
    headers = {"Authorization": "Bearer " + "t" * 40}
    try:
        with TestClient(app) as client:
            assert client.post("/api/runtime/terminal/inspect", headers=headers,
                               json={}).status_code == 403
        app.state.governed_terminal = None
        with TestClient(app) as client:
            assert client.post("/api/runtime/terminal/inspect", headers=headers,
                               json={}).status_code == 503
    finally:
        approvals.close()
