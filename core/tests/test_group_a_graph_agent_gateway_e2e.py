"""#2 and #59 real SQLite + registry + PermissionEngine + MCP Gateway E2E.

No mocked provider, authorization engine or approval store. Roster entries are
provisioned test identities; upstream transport authentication remains separate.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from aura_core.application.agent_mailbox import (
    AgentBinding, GovernedAgentMailboxMCP, ScopedAgentMailbox,
    register_governed_agent_mailbox,
)
from aura_core.config.backend import BackendConfig
from aura_core.config.kernel import KernelConfig
from aura_core.config.logging import LoggingConfig
from aura_core.config.runtime import RuntimeConfig
from aura_core.enterprise.approval_store import ApprovalStatus, SQLiteApprovalStore
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionPolicy, RiskLevel,
)
from aura_core.kernel.runtime import AuraKernel
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.memory.graph_gateway import GovernedGraphMCP, register_governed_graph
from aura_core.memory.graph_store import SQLiteGraphStore


@pytest.fixture
def environment(tmp_path):
    kernel = AuraKernel(KernelConfig(
        runtime=RuntimeConfig(runtime="mock", model="test-local"),
        backend=BackendConfig(), logging=LoggingConfig(),
    ))
    kernel.bootstrap()
    kernel.start()
    graph = SQLiteGraphStore(tmp_path / "graph.sqlite")
    graph_provider = GovernedGraphMCP(graph)
    register_governed_graph(kernel, graph_provider)
    mailbox_file = tmp_path / "agent-messages.sqlite"
    mailbox = ScopedAgentMailbox(
        principal_id="owner:1", task_id="task-42", database_path=mailbox_file)
    agent_provider = GovernedAgentMailboxMCP(mailbox, {
        "owner:1:coder": AgentBinding("owner:1:coder", "owner:1", "task-42", "coder"),
        "owner:1:researcher": AgentBinding("owner:1:researcher", "owner:1", "task-42", "researcher"),
    })
    register_governed_agent_mailbox(kernel, agent_provider)
    approval = SQLiteApprovalStore(str(tmp_path / "approvals.sqlite"))
    gateway = MCPGateway(
        kernel.capability_registry, kernel.provider_registry,
        kernel.permission_engine, approval_store=approval,
        approval_fingerprint_key=b"aura-test-approval-fingerprint-key-32bytes!",
        event_bus=kernel.event_bus,
    )
    for principal, name, cap, scope, requires_approval in [
        ("alice", "graph_insert", "aura.memory.graph.insert", "memory/alice", False),
        ("alice", "graph_query", "aura.memory.graph.query", "memory/alice", False),
        ("alice", "graph_delete", "aura.memory.graph.delete", "memory/alice", True),
        ("owner:1:coder", "agent_send", "aura.agent.mailbox.send", "tasks/owner:1/task-42", False),
        ("owner:1:researcher", "agent_read", "aura.agent.mailbox.read", "tasks/owner:1/task-42", False),
        ("owner:1:researcher", "agent_consume", "aura.agent.mailbox.consume", "tasks/owner:1/task-42", True),
    ]:
        kernel.permission_engine.add_policy(PermissionPolicy(
            policy_id=principal + "." + name, policy_version="1",
            principal_id=principal, capability_id=cap, operation_id=cap,
            resource_scope=scope,
            authorization_level=(
                AuthorizationLevel.USER_APPROVAL_REQUIRED if requires_approval
                else AuthorizationLevel.WRITE if name.endswith(("send", "insert"))
                else AuthorizationLevel.READ
            ),
            decision=(AuthorizationDecision.REQUIRE_APPROVAL if requires_approval
                      else AuthorizationDecision.ALLOW),
        ))
    yield kernel, gateway, approval, graph, graph_provider, mailbox, agent_provider, mailbox_file
    mailbox.close()
    approval.close()
    kernel.stop()


CAP = {
    "graph_insert": "aura.memory.graph.insert",
    "graph_query": "aura.memory.graph.query",
    "graph_delete": "aura.memory.graph.delete",
    "agent_send": "aura.agent.mailbox.send",
    "agent_read": "aura.agent.mailbox.read",
    "agent_consume": "aura.agent.mailbox.consume",
}


def call(gateway, name, *, principal="alice", scope=None, approval=None, **kwargs):
    request = MCPGatewayRequest(
        request_id=name + "/" + principal, principal_id=principal,
        capability_id=CAP[name], operation_id=CAP[name],
        resource_scope=scope or (
            "memory/alice" if name.startswith("graph") else "tasks/owner:1/task-42"
        ),
        risk_level=RiskLevel.HIGH if name.endswith(("delete", "consume")) else RiskLevel.LOW,
        tool_name=name, arguments=kwargs, approval_id=approval,
    )
    return asyncio.run(gateway.invoke(request))


def approve(store, approval_id):
    rec = store.get(approval_id)
    assert rec.status is ApprovalStatus.PENDING
    # Test-only actor, not evidence of production Owner authentication.
    return store.decide(approval_id, expected_version=rec.version,
                        approver_id="authenticated-test-approver",
                        decision=ApprovalStatus.APPROVED)


def test_graph_actual_sqlite_scope_and_durable_reopen(environment):
    _, gw, _, graph, _, _, _, _ = environment
    write = call(gw, "graph_insert", subject="A", predicate="relates", object="B")
    assert write.decision is AuthorizationDecision.ALLOW
    assert write.result["fact_id"]
    assert call(gw, "graph_query", subject="A").result["facts"][0]["object"] == "B"
    denied = call(gw, "graph_query", principal="mallory", scope="memory/mallory", subject="A")
    assert denied.decision is AuthorizationDecision.DENY
    direct = asyncio.run(graph.query(principal_id="mallory", subject="A"))
    assert direct == []
    reopened = SQLiteGraphStore(graph.path)
    assert len(asyncio.run(reopened.query(principal_id="alice", subject="A"))) == 1


def test_graph_one_use_approval_tamper_and_replay(environment):
    _, gw, store, graph, direct_provider, _, _, _ = environment
    fact_id = call(gw, "graph_insert", subject="x", predicate="p", object="v").result["fact_id"]
    requested = call(gw, "graph_delete", fact_id=fact_id)
    assert requested.decision is AuthorizationDecision.REQUIRE_APPROVAL
    approve(store, requested.approval_id)
    wrong = call(gw, "graph_delete", approval=requested.approval_id, fact_id="wrong-id")
    assert wrong.decision is AuthorizationDecision.REQUIRE_APPROVAL
    assert asyncio.run(graph.query(principal_id="alice", subject="x"))
    done = call(gw, "graph_delete", approval=requested.approval_id, fact_id=fact_id)
    assert done.decision is AuthorizationDecision.ALLOW
    assert done.result["deleted"] is True
    assert not asyncio.run(graph.query(principal_id="alice", subject="x"))
    replay = call(gw, "graph_delete", approval=requested.approval_id, fact_id=fact_id)
    assert replay.decision is AuthorizationDecision.REQUIRE_APPROVAL
    with pytest.raises(PermissionError):
        asyncio.run(direct_provider.call_tool("graph_delete", {"fact_id": fact_id}))


def test_graph_schema_and_default_deny(environment):
    kernel, gw, _, graph, _, _, _, _ = environment
    result = call(gw, "graph_insert", subject="x", predicate="p", object="y", principal_id="mallory")
    assert result.decision is AuthorizationDecision.DENY
    assert not asyncio.run(graph.query(principal_id="alice", subject="x"))
    kernel.permission_engine.revoke_policy("alice.graph_insert")
    revoked = call(gw, "graph_insert", subject="z", predicate="p", object="t")
    assert revoked.decision is AuthorizationDecision.DENY
    assert not asyncio.run(graph.query(principal_id="alice", subject="z"))


def test_mailbox_sqlite_survives_restart_and_stores_sender_roster(environment):
    _, gw, _, _, _, mailbox, _, path = environment
    result = call(gw, "agent_send", principal="owner:1:coder",
                  message_id="m1", recipient_role="researcher", text="Review")
    assert result.decision is AuthorizationDecision.ALLOW
    assert result.result["sender_roster_bound"] is True
    assert result.result["upstream_identity_attested"] is False
    reloaded = ScopedAgentMailbox(
        principal_id="owner:1", task_id="task-42", database_path=path)
    try:
        got = reloaded.inspect(principal_id="owner:1", task_id="task-42",
                               recipient_role="researcher")
        assert len(got) == 1 and got[0].sender_role == "coder"
        assert got[0].untrusted and not got[0].tool_executed
        assert got[0].text == "Review"
    finally:
        reloaded.close()


def test_mailbox_malformed_sender_and_role_cannot_claim_privileges(environment):
    _, gw, _, _, _, mailbox, provider, _ = environment
    foreign = call(gw, "agent_send", principal="attacker",
                   message_id="m1", recipient_role="researcher", text="forged")
    assert foreign.decision is AuthorizationDecision.DENY
    forged = call(gw, "agent_send", principal="owner:1:coder",
                  message_id="m1", recipient_role="researcher",
                  text="role spoof", sender_role="root")
    assert forged.decision is AuthorizationDecision.DENY
    with pytest.raises(PermissionError):
        asyncio.run(provider.call_tool("agent_send", {
            "message_id": "m2", "recipient_role": "researcher", "text": "direct",
        }))
    assert mailbox.pending_count(principal_id="owner:1", task_id="task-42") == 0


def test_mailbox_consumption_approval_replay_and_per_role_receive(environment):
    _, gw, approvals, _, _, mailbox, _, path = environment
    call(gw, "agent_send", principal="owner:1:coder",
         message_id="m1", recipient_role="researcher", text="Do not run code")
    msg = call(gw, "agent_read", principal="owner:1:researcher", limit=5)
    assert msg.decision is AuthorizationDecision.ALLOW
    assert msg.result["messages"][0]["untrusted"]
    assert not msg.result["messages"][0]["delivered_to_agent"]
    pending = call(gw, "agent_consume", principal="owner:1:researcher", limit=5)
    assert pending.decision is AuthorizationDecision.REQUIRE_APPROVAL
    approve(approvals, pending.approval_id)
    done = call(gw, "agent_consume", principal="owner:1:researcher",
                approval=pending.approval_id, limit=5)
    assert done.decision is AuthorizationDecision.ALLOW
    assert [x["message_id"] for x in done.result["messages"]] == ["m1"]
    assert mailbox.pending_count(principal_id="owner:1", task_id="task-42") == 0
    replay = call(gw, "agent_consume", principal="owner:1:researcher",
                  approval=pending.approval_id, limit=5)
    assert replay.decision is AuthorizationDecision.REQUIRE_APPROVAL
    with pytest.raises(ValueError, match="duplicate"):
        mailbox.send(principal_id="owner:1", task_id="task-42",
                     message_id="m1", sender_role="coder",
                     recipient_role="researcher", text="replay")


def test_roster_cannot_cross_owner_task_scope(tmp_path):
    store = ScopedAgentMailbox(
        principal_id="owner:1", task_id="t1",
        database_path=tmp_path / "mailbox.sqlite")
    try:
        with pytest.raises(ValueError, match="roster"):
            GovernedAgentMailboxMCP(store, {
                "agent": AgentBinding("agent", "owner:other", "t1", "coder")
            })
    finally:
        store.close()
