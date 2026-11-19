"""Actual persisted TaskStateMachine command chains and nested approval tests."""
import asyncio
import hashlib
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aura_core.application.task_state_machine import TaskState, TaskStateMachine
from aura_core.application.governed_command_sequences import (
    GovernedCommandSequences, CommandSequenceDenied, CommandSequenceUnavailable,
    register_command_sequences, sequence_router,
)
from aura_core.enterprise.approval_store import ApprovalStatus, SQLiteApprovalStore
from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.events import EventBus
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy,
)
from aura_core.kernel.services import ServiceRegistry
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.provider import ProviderRegistry
from aura_core.providers.docker_terminal_mcp import (
    DockerSandboxEngine, GovernedDockerTerminal, TerminalCommand, register_docker_terminal,
)

IMAGE = "alpine@sha256:" + "b" * 64


def run(coro):
    return asyncio.run(coro)


def _system(tmp_path, *, plan=True, advance=True, terminal=True):
    bus = EventBus()
    store = TaskStateMachine(tmp_path / "tasks.sqlite3", event_bus=bus)
    services = ServiceRegistry()
    providers = ProviderRegistry(services)
    capabilities = CapabilityRegistry(services)
    cli = Path(sys.executable).resolve()
    engine = DockerSandboxEngine(
        docker_executable=str(cli), docker_sha256=hashlib.sha256(cli.read_bytes()).hexdigest(),
    )
    local_terminal = register_docker_terminal(
        services=services, providers=providers, capabilities=capabilities,
        event_bus=bus, engine=engine,
        commands=(TerminalCommand("first", IMAGE, ("pwd",)),
                  TerminalCommand("second", IMAGE, ("pwd",))),
    )
    permissions = PermissionEngine(capabilities)
    for cap, scope, needed in (
        ("workflow.commands.plan", "workflow/commands/plan", plan),
        ("workflow.commands.advance", "workflow/commands/advance", advance),
        ("terminal.sandbox.execute", "terminal/sandbox/first", terminal),
        ("terminal.sandbox.execute", "terminal/sandbox/second", terminal),
    ):
        if needed:
            permissions.add_policy(PermissionPolicy(
                policy_id="owner." + cap + scope, policy_version="1.0.0",
                principal_id="owner", capability_id=cap, operation_id=cap,
                resource_scope=scope,
                authorization_level=(AuthorizationLevel.USER_APPROVAL_REQUIRED
                    if cap == "terminal.sandbox.execute" else AuthorizationLevel.EXECUTE),
                decision=(AuthorizationDecision.REQUIRE_APPROVAL
                    if cap == "terminal.sandbox.execute" else AuthorizationDecision.ALLOW),
            ))
    approvals = SQLiteApprovalStore(str(tmp_path / "approvals.sqlite3"))
    gateway = MCPGateway(
        capabilities, providers, permissions, event_bus=bus,
        approval_store=approvals, approval_fingerprint_key=b"z" * 32,
    )
    terminal_reader = GovernedDockerTerminal(gateway, principal_id="owner")
    backend = register_command_sequences(
        services=services, providers=providers, capabilities=capabilities,
        event_bus=bus, tasks=store, terminal=terminal_reader,
        hmac_key=b"s" * 32, allowed_command_ids=("first", "second"),
    )
    reader = GovernedCommandSequences(gateway, principal_id="owner")
    return bus, store, permissions, approvals, reader, backend, local_terminal, engine, gateway


def _approve(store, receipt):
    row = store.get(receipt)
    assert row is not None and row.status is ApprovalStatus.PENDING
    store.decide(receipt, expected_version=row.version,
                 approver_id="human:owner", decision=ApprovalStatus.APPROVED)


def test_real_persisted_sqlite_dependency_and_step_by_step_manual_approval(tmp_path):
    bus, store, engine, approvals, reader, backend, terminal, sandbox, gateway = _system(tmp_path)
    try:
        plan = run(reader.plan(["first", "second"]))
        assert plan.state == "created" and len(plan.task_ids) == 2
        first, second = plan.task_ids
        assert store.get(first, principal_id="owner").state == TaskState.READY
        assert store.get(second, principal_id="owner").state == TaskState.PENDING
        with pytest.raises(CommandSequenceUnavailable):
            run(reader.advance(second))
        pending = run(reader.advance(first))
        assert pending.state == "approval_required"
        assert store.get(first, principal_id="owner").state == TaskState.READY
        assert store.get(second, principal_id="owner").state == TaskState.PENDING
        _approve(approvals, pending.approval_id)
        # Unit-level positive state-machine contract; actual subprocess execution
        # is separately exercised by #27, live Docker smoke requires an image.
        sandbox.run = lambda spec: {
            "command_id": spec.command_id, "exit_code": 0,
            "stdout": "/workspace\n", "trust": "UNTRUSTED_CONTAINER_OUTPUT",
        }
        done = run(reader.advance(first, approval_id=pending.approval_id))
        assert done.state == "succeeded"
        assert approvals.get(pending.approval_id).status == ApprovalStatus.CONSUMED
        assert store.get(first, principal_id="owner").state == TaskState.SUCCEEDED
        assert store.get(second, principal_id="owner").state == TaskState.READY
        with pytest.raises(CommandSequenceUnavailable):
            run(reader.advance(first))
        assert store.get(second, principal_id="owner").state == TaskState.READY
        next_pending = run(reader.advance(second))
        assert next_pending.state == "approval_required"
        assert next_pending.approval_id != pending.approval_id
        _approve(approvals, next_pending.approval_id)
        assert run(reader.advance(second, approval_id=next_pending.approval_id)).state == "succeeded"
        assert store.get(second, principal_id="owner").state == TaskState.SUCCEEDED
    finally:
        approvals.close()
        store.close()


def test_real_failing_local_terminal_blocks_dependents_without_auto_retry(tmp_path):
    _, store, _, approvals, reader, _, _, _, _ = _system(tmp_path)
    try:
        first, second = run(reader.plan(["first", "second"])).task_ids
        pending = run(reader.advance(first))
        _approve(approvals, pending.approval_id)
        # This runs a real OS process via DockerSandboxEngine; sys.executable
        # is intentionally not Docker, so no sandboxing success is claimed.
        failed = run(reader.advance(first, approval_id=pending.approval_id))
        assert failed.state == "failed"
        assert store.get(first, principal_id="owner").state == TaskState.FAILED
        assert store.get(second, principal_id="owner").state == TaskState.BLOCKED
        with pytest.raises(CommandSequenceUnavailable):
            run(reader.advance(first, approval_id=pending.approval_id))
    finally:
        approvals.close()
        store.close()


def test_no_extra_approval_or_missing_terminal_policy_is_fail_closed(tmp_path):
    _, store, _, approvals, reader, _, _, _, _ = _system(tmp_path, terminal=False)
    try:
        step = run(reader.plan(["first"])).task_ids[0]
        with pytest.raises(CommandSequenceUnavailable):
            run(reader.advance(step))
        assert store.get(step, principal_id="owner").state == TaskState.READY
    finally:
        approvals.close()
        store.close()


def test_default_deny_plan_and_advance_are_separate(tmp_path):
    _, store, _, approvals, reader, _, _, _, _ = _system(tmp_path, plan=False)
    try:
        with pytest.raises(CommandSequenceDenied):
            run(reader.plan(["first"]))
    finally:
        approvals.close()
        store.close()
    _, store, _, approvals, reader, _, _, _, _ = _system(tmp_path, advance=False)
    try:
        step = run(reader.plan(["first"])).task_ids[0]
        with pytest.raises(CommandSequenceDenied):
            run(reader.advance(step))
        assert store.get(step, principal_id="owner").state == TaskState.READY
    finally:
        approvals.close()
        store.close()


def test_direct_provider_bypass_and_command_injection_fails(tmp_path):
    _, store, _, approvals, reader, backend, _, _, _ = _system(tmp_path)
    try:
        with pytest.raises(CommandSequenceDenied):
            run(backend.call_tool("plan_terminal_sequence", {"commands": ["first"]}))
        with pytest.raises(CommandSequenceUnavailable):
            run(reader.plan(["shell;rm -rf /"]))
        with pytest.raises(ValueError):
            run(reader.plan([]))
    finally:
        approvals.close()
        store.close()


def test_foreign_owner_and_unsealed_forged_task_denied(tmp_path):
    _, store, _, approvals, reader, backend, _, _, gateway = _system(tmp_path)
    try:
        step = run(reader.plan(["first"])).task_ids[0]
        intruder = GovernedCommandSequences(gateway, principal_id="intruder")
        with pytest.raises(CommandSequenceDenied):
            run(intruder.advance(step))
        forged = store.create_task(principal_id="owner", goal="aura.command-sequence.v1|first|0")
        with pytest.raises(CommandSequenceUnavailable):
            run(reader.advance(forged.task_id))
        assert store.get(step, principal_id="owner").state == TaskState.READY
    finally:
        approvals.close()
        store.close()


def test_durable_plan_survives_restart_without_execution(tmp_path):
    _, store, _, approvals, reader, backend, _, _, _ = _system(tmp_path)
    try:
        plan = run(reader.plan(["first", "second"]))
        store.close()
        reloaded = TaskStateMachine(tmp_path / "tasks.sqlite3")
        backend._tasks = reloaded
        assert reloaded.get(plan.task_ids[0], principal_id="owner").state == TaskState.READY
        assert reloaded.get(plan.task_ids[1], principal_id="owner").state == TaskState.PENDING
        assert run(reader.advance(plan.task_ids[0])).state == "approval_required"
        assert reloaded.get(plan.task_ids[0], principal_id="owner").state == TaskState.READY
        reloaded.close()
    finally:
        approvals.close()


def test_http_bearer_and_gateway_enforce_explicit_manual_step(tmp_path):
    _, store, _, approvals, reader, backend, _, _, _ = _system(tmp_path)
    web = FastAPI()
    web.state.http_bearer_token = "t" * 40
    web.state.http_principal_id = "owner"
    web.state.governed_command_sequences = reader
    web.include_router(sequence_router)
    auth = {"Authorization": "Bearer " + "t" * 40}
    try:
        with TestClient(web) as client:
            assert client.post("/api/runtime/command-sequences", json={"commands": ["first"]}).status_code == 401
            assert client.post("/api/runtime/command-sequences", headers=auth,
                               json={"commands": ["first"], "shell": "rm"}).status_code == 422
            plan = client.post("/api/runtime/command-sequences", headers=auth,
                               json={"commands": ["first"]})
            assert plan.status_code == 200
            step = plan.json()["task_ids"][0]
            pending = client.post(f"/api/runtime/command-sequences/{step}/advance",
                                  headers=auth, json={})
            assert pending.status_code == 202
            assert pending.json()["state"] == "approval_required"
            assert "no-store" in pending.headers["cache-control"]
            assert store.get(step, principal_id="owner").state == TaskState.READY
    finally:
        store.close()
        approvals.close()
