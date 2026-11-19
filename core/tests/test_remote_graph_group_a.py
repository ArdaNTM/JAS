"""Live PostgreSQL 16 + actual PermissionEngine/MCPGateway erasure test.

Only runs in Remote Persistence CI with AURA_TEST_DATABASE_URL; no fake DB.
The approval decision uses a *test* authenticated actor, not Owner acceptance.
"""
from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest

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
from aura_core.memory.graph_store import PostgreSQLGraphStore

URL = os.environ.get("AURA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="real PostgreSQL service not present")


def test_postgres_graph_gateway_principal_scope_durable_delete_and_replay():
    async def scenario():
        scope = "acceptance-" + uuid4().hex
        alice, bob = scope + "-alice", scope + "-bob"
        store = PostgreSQLGraphStore(URL)
        await store.initialize()
        kernel = AuraKernel(KernelConfig(
            runtime=RuntimeConfig(runtime="mock", model="test-local"),
            backend=BackendConfig(), logging=LoggingConfig(),
        ))
        kernel.bootstrap()
        kernel.start()
        register_governed_graph(kernel, GovernedGraphMCP(store))
        approvals = SQLiteApprovalStore(":memory:")
        gateway = MCPGateway(
            kernel.capability_registry, kernel.provider_registry,
            kernel.permission_engine, approval_store=approvals,
            approval_fingerprint_key=b"aura-graph-remote-test-key-32-bytes!",
        )
        caps = {
            "graph_insert": "aura.memory.graph.insert",
            "graph_query": "aura.memory.graph.query",
            "graph_delete": "aura.memory.graph.delete",
            "graph_soft_delete": "aura.memory.graph.soft_delete",
            "graph_restore": "aura.memory.graph.restore",
        }
        for tool, cap in caps.items():
            kernel.permission_engine.add_policy(PermissionPolicy(
                policy_id=scope+"-"+tool, policy_version="1",
                principal_id=alice, capability_id=cap, operation_id=cap,
                resource_scope="memory/"+alice,
                authorization_level=(
                    AuthorizationLevel.USER_APPROVAL_REQUIRED
                    if tool in {"graph_delete", "graph_soft_delete", "graph_restore"}
                    else AuthorizationLevel.WRITE
                ),
                decision=(AuthorizationDecision.REQUIRE_APPROVAL
                          if tool in {"graph_delete", "graph_soft_delete", "graph_restore"}
                          else AuthorizationDecision.ALLOW),
            ))

        async def call(tool, *, principal=alice, approval=None, **args):
            cap = caps[tool]
            return await gateway.invoke(MCPGatewayRequest(
                request_id=scope+"-"+tool, principal_id=principal,
                capability_id=cap, operation_id=cap,
                resource_scope="memory/"+principal,
                risk_level=RiskLevel.HIGH if tool in {"graph_delete", "graph_soft_delete", "graph_restore"}
                else RiskLevel.LOW,
                tool_name=tool, arguments=args, approval_id=approval,
            ))

        try:
            entry = await call("graph_insert", subject="real-pg-"+scope,
                               predicate="relates", object="data")
            assert entry.decision is AuthorizationDecision.ALLOW
            fact_id = entry.result["fact_id"]
            foreign = await call("graph_query", principal=bob, subject="real-pg-"+scope)
            assert foreign.decision is AuthorizationDecision.DENY
            assert (await store.query(principal_id=bob, subject="real-pg-"+scope)) == []

            pending = await call("graph_delete", fact_id=fact_id)
            assert pending.decision is AuthorizationDecision.REQUIRE_APPROVAL
            assert len(await store.query(principal_id=alice, subject="real-pg-"+scope)) == 1
            rec = approvals.get(pending.approval_id)
            approvals.decide(rec.approval_id, expected_version=rec.version,
                             approver_id="remote-ci-test-approver",
                             decision=ApprovalStatus.APPROVED)
            success = await call("graph_delete", fact_id=fact_id,
                                 approval=pending.approval_id)
            assert success.decision is AuthorizationDecision.ALLOW
            assert success.result["deleted"] is True
            assert await store.query(principal_id=alice, subject="real-pg-"+scope) == []
            # New transactional soft-delete/restore on a second durable PostgreSQL fact.
            second = await call("graph_insert", subject="other-"+scope,
                                predicate="link", object="tail")
            second_id = second.result["fact_id"]
            tombstone = await call("graph_soft_delete", fact_id=second_id)
            assert tombstone.decision is AuthorizationDecision.REQUIRE_APPROVAL
            pending_record = approvals.get(tombstone.approval_id)
            approvals.decide(pending_record.approval_id,
                             expected_version=pending_record.version,
                             approver_id="remote-ci-test-approver",
                             decision=ApprovalStatus.APPROVED)
            changed = await call("graph_soft_delete", fact_id=second_id,
                                 approval=tombstone.approval_id)
            assert changed.decision is AuthorizationDecision.ALLOW
            assert changed.result["soft_deleted"]
            reopened_tombstone = PostgreSQLGraphStore(URL)
            try:
                assert await reopened_tombstone.query(
                    principal_id=alice, subject="other-"+scope) == []
                recovery = await call("graph_restore", fact_id=second_id)
                assert recovery.decision is AuthorizationDecision.REQUIRE_APPROVAL
                approval_record = approvals.get(recovery.approval_id)
                approvals.decide(approval_record.approval_id,
                                 expected_version=approval_record.version,
                                 approver_id="remote-ci-test-approver",
                                 decision=ApprovalStatus.APPROVED)
                outcome = await call("graph_restore", fact_id=second_id,
                                     approval=recovery.approval_id)
                assert outcome.decision is AuthorizationDecision.ALLOW
                assert outcome.result["restored"]
                assert (await reopened_tombstone.query(
                    principal_id=alice, subject="other-"+scope))[0]["fact_id"] == second_id
                log = await reopened_tombstone.lifecycle_audit(
                    principal_id=alice, fact_id=second_id)
                assert [x["action"] for x in log] == ["soft_delete", "restore"]
                assert await reopened_tombstone.lifecycle_audit(
                    principal_id=bob, fact_id=second_id) == ()
            finally:
                await reopened_tombstone.close()
            replay = await call("graph_delete", fact_id=fact_id,
                                approval=pending.approval_id)
            assert replay.decision is AuthorizationDecision.REQUIRE_APPROVAL
            # Open a second live PostgreSQL connection to verify durability.
            reopened = PostgreSQLGraphStore(URL)
            try:
                assert await reopened.query(
                    principal_id=alice, subject="real-pg-"+scope) == []
            finally:
                await reopened.close()
        finally:
            approvals.close()
            await store.close()
            kernel.stop()
    asyncio.run(scenario())
