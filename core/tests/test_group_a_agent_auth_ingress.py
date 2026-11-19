"""#59: real signed agent ingress / durable replay / role-specific Gateway dispatch."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from dataclasses import replace

import pytest

from aura_core.application.agent_mailbox import (
    AgentBinding, GovernedAgentMailboxMCP, ScopedAgentMailbox,
    register_governed_agent_mailbox,
)
from aura_core.application.agent_credentials import (
    AuthenticatedAgentGateway, SignedAgentRequest, canonical_agent_auth_payload,
)
from aura_core.config.backend import BackendConfig
from aura_core.config.kernel import KernelConfig
from aura_core.config.logging import LoggingConfig
from aura_core.config.runtime import RuntimeConfig
from aura_core.enterprise.approval_store import ApprovalStatus, SQLiteApprovalStore
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionPolicy,
)
from aura_core.kernel.runtime import AuraKernel
from aura_core.mcp.gateway import MCPGateway

CODER = "owner:1:coder"
RESEARCHER = "owner:1:researcher"
KEYS = {CODER: b"local-coder-auth-key-32bytes-00000000",
        RESEARCHER: b"local-researcher-auth-key-32bytes!!"}


def signed(principal, tool, args, *, nonce, approval=None, key=None, ts=None):
    timestamp = int(time.time()) if ts is None else ts
    material = canonical_agent_auth_payload(
        principal, tool, args, nonce, timestamp, approval)
    signature = hmac.new(key or KEYS[principal], material, hashlib.sha256).hexdigest()
    return SignedAgentRequest(principal, tool, args, timestamp, nonce,
                              signature, approval)


@pytest.fixture
def signed_environment(tmp_path):
    kernel = AuraKernel(KernelConfig(
        runtime=RuntimeConfig(runtime="mock", model="local-test"),
        backend=BackendConfig(), logging=LoggingConfig(),
    ))
    kernel.bootstrap()
    kernel.start()
    mailbox = ScopedAgentMailbox(
        principal_id="owner:1", task_id="task-42",
        database_path=tmp_path / "mailbox.sqlite")
    provider = GovernedAgentMailboxMCP(mailbox, {
        CODER: AgentBinding(CODER, "owner:1", "task-42", "coder"),
        RESEARCHER: AgentBinding(RESEARCHER, "owner:1", "task-42", "researcher"),
    })
    register_governed_agent_mailbox(kernel, provider)
    approval = SQLiteApprovalStore(str(tmp_path / "approval.sqlite"))
    gateway = MCPGateway(
        kernel.capability_registry, kernel.provider_registry,
        kernel.permission_engine, approval_store=approval,
        approval_fingerprint_key=b"local-agent-request-fingerprint-32bytes!")
    for principal, name, cap, is_destructive in (
        (CODER, "send", "aura.agent.mailbox.send", False),
        (RESEARCHER, "read", "aura.agent.mailbox.read", False),
        (RESEARCHER, "consume", "aura.agent.mailbox.consume", True),
    ):
        kernel.permission_engine.add_policy(PermissionPolicy(
            policy_id=principal+"-"+name, policy_version="1",
            principal_id=principal, capability_id=cap, operation_id=cap,
            resource_scope="tasks/owner:1/task-42",
            authorization_level=(AuthorizationLevel.USER_APPROVAL_REQUIRED
                                 if is_destructive else AuthorizationLevel.READ),
            decision=(AuthorizationDecision.REQUIRE_APPROVAL if is_destructive
                      else AuthorizationDecision.ALLOW),
        ))
    ingress = AuthenticatedAgentGateway(
        gateway, provider, signing_keys=KEYS,
        nonce_database=tmp_path / "auth_nonces.sqlite")
    yield ingress, approval, mailbox, gateway, provider, tmp_path
    ingress.close()
    approval.close()
    mailbox.close()
    kernel.stop()


def test_signed_ingress_authenticated_send_read_and_durable_replay(signed_environment):
    ingress, approvals, mailbox, gateway, provider, tmp_path = signed_environment
    message = {"message_id": "m1", "recipient_role": "researcher",
               "text": "Review this untrusted evidence"}
    sent = asyncio.run(ingress.invoke(signed(CODER, "agent_send", message, nonce="1"*32)))
    assert sent.decision is AuthorizationDecision.ALLOW
    assert sent.result["queued"] and sent.result["sender_roster_bound"]
    with pytest.raises(PermissionError, match="replayed"):
        asyncio.run(ingress.invoke(signed(CODER, "agent_send", message, nonce="1"*32)))
    reader = asyncio.run(ingress.invoke(signed(
        RESEARCHER, "agent_read", {}, nonce="2"*32)))
    assert reader.decision is AuthorizationDecision.ALLOW
    assert reader.result["messages"][0]["text"] == message["text"]
    assert reader.result["messages"][0]["untrusted"]

    # A new real SQLite connection observes the same durable nonce ledger.
    resumed = AuthenticatedAgentGateway(
        gateway, provider, signing_keys=KEYS,
        nonce_database=tmp_path / "auth_nonces.sqlite")
    try:
        with pytest.raises(PermissionError, match="replayed"):
            asyncio.run(resumed.invoke(signed(CODER, "agent_send", message, nonce="1"*32)))
    finally:
        resumed.close()


def test_signed_ingress_tamper_signature_stale_time_and_cross_principal(signed_environment):
    ingress, approvals, mailbox, gateway, provider, tmp_path = signed_environment
    message = {"message_id": "m1", "recipient_role": "researcher", "text": "safe"}
    valid = signed(CODER, "agent_send", message, nonce="3"*32)
    with pytest.raises(PermissionError, match="signature"):
        asyncio.run(ingress.invoke(replace(valid, arguments={**message, "text": "evil"})))
    with pytest.raises(PermissionError, match="signature"):
        asyncio.run(ingress.invoke(replace(valid, principal_id=RESEARCHER)))
    with pytest.raises(PermissionError, match="stale"):
        asyncio.run(ingress.invoke(signed(
            CODER, "agent_send", message, nonce="4"*32,
            ts=int(time.time())-3600)))
    assert mailbox.pending_count(principal_id="owner:1", task_id="task-42") == 0


def test_signed_ingress_consumed_approval_is_one_time(signed_environment):
    ingress, approvals, mailbox, gateway, provider, _ = signed_environment
    msg = {"message_id": "x1", "recipient_role": "researcher", "text": "read me"}
    assert asyncio.run(ingress.invoke(signed(
        CODER, "agent_send", msg, nonce="5"*32))).result["queued"]
    request = signed(RESEARCHER, "agent_consume", {"limit": 1}, nonce="6"*32)
    pending = asyncio.run(ingress.invoke(request))
    assert pending.decision is AuthorizationDecision.REQUIRE_APPROVAL
    rec = approvals.get(pending.approval_id)
    approvals.decide(rec.approval_id, expected_version=rec.version,
                     approver_id="verified-test-actor", decision=ApprovalStatus.APPROVED)
    consumed = asyncio.run(ingress.invoke(signed(
        RESEARCHER, "agent_consume", {"limit": 1},
        nonce="7"*32, approval=pending.approval_id)))
    assert consumed.decision is AuthorizationDecision.ALLOW
    assert [x["message_id"] for x in consumed.result["messages"]] == ["x1"]
    assert mailbox.pending_count(principal_id="owner:1", task_id="task-42") == 0
    again = asyncio.run(ingress.invoke(signed(
        RESEARCHER, "agent_consume", {"limit": 1},
        nonce="8"*32, approval=pending.approval_id)))
    assert again.decision is AuthorizationDecision.REQUIRE_APPROVAL


def test_hmac_signature_from_separate_python_process_passes_existing_gateway(
        signed_environment):
    import json
    import subprocess
    import sys

    ingress, _, mailbox, _, _, _ = signed_environment
    data = {"message_id": "process-1", "recipient_role": "researcher",
            "text": "signed by a separate real Python interpreter"}
    nonce = "a" * 32
    timestamp = int(time.time())
    material = canonical_agent_auth_payload(CODER, "agent_send",
                                             data, nonce, timestamp)
    script = (
        "import json,sys,hmac,hashlib\n"
        "x=json.loads(sys.stdin.read())\n"
        "print(hmac.new(bytes.fromhex(x['key']),bytes.fromhex(x['payload']),"
        "hashlib.sha256).hexdigest())\n"
    )
    worker = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps({"key": KEYS[CODER].hex(), "payload": material.hex()}),
        text=True, capture_output=True, timeout=10, check=True,
    )
    signature = worker.stdout.strip()
    request = SignedAgentRequest(
        CODER, "agent_send", data, timestamp, nonce, signature)
    result = asyncio.run(ingress.invoke(request))
    assert result.decision is AuthorizationDecision.ALLOW
    assert result.result["queued"] is True
    assert mailbox.pending_count(principal_id="owner:1", task_id="task-42") == 1
    with pytest.raises(PermissionError, match="replayed"):
        asyncio.run(ingress.invoke(request))
    # The same signature cannot authorize a different provisioned principal.
    with pytest.raises(PermissionError, match="signature"):
        asyncio.run(ingress.invoke(replace(request, principal_id=RESEARCHER)))
