"""End-to-end metadata-only activation/rollback with real signed owner receipts.

An injected attestation verifier represents an independently provisioned
attestor; these tests do NOT claim a real Docker runner or Windows Hello.
"""
from __future__ import annotations

import hashlib
import sqlite3

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient

from aura_core.enterprise.approval_store import SQLiteApprovalStore, ApprovalStatus
from aura_core.evolution.activation_api import create_governed_activation_app
from aura_core.evolution.owner_receipt import OwnerReceiptIssuer, DurableOwnerReceiptConsumer
from aura_core.evolution.skill_registry import GovernedSkillRegistry, SkillBinding
from aura_core.kernel.capabilities import (
    CapabilityRegistry, CapabilityDefinition, CapabilityCategory, ProviderType,
)
from aura_core.kernel.permissions import (
    PermissionEngine, PermissionPolicy, AuthorizationDecision,
    AuthorizationLevel, RiskLevel,
)
from aura_core.kernel.services import ServiceRegistry, ServiceDefinition, ServiceCategory
from aura_core.mcp.provider import ProviderRegistry, ProviderDefinition


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def governed(tmp_path):
    services = ServiceRegistry()
    mcp = ServiceDefinition(name="mcp", version="1", provider="review",
                            category=ServiceCategory.MCP)
    services.register(mcp, object())
    providers = ProviderRegistry(services)
    providers.register(ProviderDefinition(
        provider_id="review.mcp", name="Existing MCP", version="1",
        service_id=mcp.service_id,
    ), object())
    caps = CapabilityRegistry(services)
    caps.register(CapabilityDefinition(
        capability_id="ReviewedTool", name="Pre-registered", version="1",
        description="Already registered MCP provider", provider_id="review.mcp",
        provider_type=ProviderType.MCP, category=CapabilityCategory.DIAGNOSTICS,
        tool_name="safe_read", risk_level="low",
    ))
    caps.register(CapabilityDefinition(
        capability_id="GovernedSkillActivation", name="Owner", version="1",
        description="High-risk owner governance", provider_id="review.mcp",
        provider_type=ProviderType.MCP, category=CapabilityCategory.SECURITY,
        tool_name="owner_review", risk_level="critical",
    ))
    policy = sha(b"pinned JAS policy")
    permission = PermissionEngine(caps)
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    ledger = tmp_path / "owner-replay.sqlite"
    sqlite3.connect(ledger).close()
    ledger.chmod(0o600)
    owner = DurableOwnerReceiptConsumer(
        trusted_public_keys={"owner-operator": public},
        policy_digest=policy, permissions=permission, ledger_path=ledger,
    )
    issuer = OwnerReceiptIssuer(
        key_id="owner-operator", private_key=key, policy_digest=policy,
    )
    validated = set()
    attestations = set()
    registry = GovernedSkillRegistry(
        capabilities=caps, providers=providers,
        validation_verifier=lambda digest, receipt: (digest, receipt) in validated,
        signed_attestation_verifier=lambda binding, receipt:
            (binding.review_digest, receipt) in attestations,
        owner_receipt_consumer=owner,
    )
    app = create_governed_activation_app(registry=registry, owner_receipts=owner)
    with SQLiteApprovalStore(":memory:") as approvals:
        with TestClient(app, base_url="http://localhost:8767") as client:
            state = {
                "registry": registry, "client": client,
                "owner": owner, "issuer": issuer,
                "validated": validated, "attestations": attestations,
                "permission": permission, "approvals": approvals,
                "policy": policy,
                "count": 0,
            }
            yield state
    owner.close()


def binding(version: str) -> SkillBinding:
    return SkillBinding(
        name="safe_reader", version=version,
        source_sha256=sha(version.encode()),
        capability_id="ReviewedTool", provider_id="review.mcp",
        operation_id="read", tool_name="safe_read",
        resource_scope="diagnostic:public", risk_level=RiskLevel.LOW,
    )


def stage(s, item, receipt):
    s["registry"].stage(item)
    s["validated"].add((item.source_sha256, receipt))
    s["attestations"].add((item.review_digest, receipt))
    assert s["registry"].validate(item.name, sandbox_receipt=receipt)


def owner_proof(s, operation, item):
    s["count"] += 1
    s["permission"].add_policy(PermissionPolicy(
        policy_id="jas:owner-approval-" + str(s["count"]),
        policy_version="1.0.0",
        principal_id="local_owner",
        capability_id="GovernedSkillActivation",
        operation_id=operation,
        resource_scope="evolution:skill:" + item.review_digest,
        authorization_level=AuthorizationLevel.USER_APPROVAL_REQUIRED,
        decision=AuthorizationDecision.REQUIRE_APPROVAL,
    ))
    request = s["approvals"].create(
        principal_id="local_owner", capability_id="GovernedSkillActivation",
        operation_id=operation,
        resource_scope="evolution:skill:" + item.review_digest,
        request_fingerprint=item.review_digest,
        policy_digest=s["policy"],
    )
    decision = s["approvals"].decide(
        request.approval_id, expected_version=request.version,
        approver_id="human:local-owner", decision=ApprovalStatus.APPROVED,
    )
    return s["issuer"].issue(decision)


def post(s, action, receipt):
    return s["client"].post(
        "/api/activation/version",
        json={"name": "safe_reader", "action": action,
              "owner_receipt": receipt},
        headers={"Origin": "http://localhost:8766",
                 "Sec-Fetch-Site": "same-site"},
    )


def test_real_signed_receipt_is_one_shot_and_activation_never_imports_python(governed):
    s = governed
    v1 = binding("1.0.0")
    proof = owner_proof(s, "activate", v1)
    assert post(s, "activate", proof).status_code == 403  # not staged
    s["registry"].stage(v1)
    assert post(s, "activate", proof).status_code == 403  # not validated
    s["validated"].add((v1.source_sha256, "proof-1"))
    with pytest.raises(PermissionError):
        s["registry"].validate(v1.name, sandbox_receipt="proof-1")
    s["attestations"].add((v1.review_digest, "proof-1"))
    s["registry"].validate(v1.name, sandbox_receipt="proof-1")
    response = post(s, "activate", proof)
    assert response.status_code == 200, response.text
    assert response.json()["tool_executed"] is False
    assert response.json()["generated_python_loaded"] is False
    assert response.json()["revision"] == s["registry"].catalog()[0]["revision"]
    assert post(s, "activate", proof).status_code == 403  # persistent one-use
    assert post(s, "rollback", proof).status_code == 403  # operation-bound
    assert s["registry"].catalog()[0]["version"] == "1.0.0"


def test_versioned_rollback_and_revoke_need_fresh_operation_bound_receipts(governed):
    s = governed
    v1 = binding("1.0.0")
    stage(s, v1, "sandbox-1")
    assert post(s, "activate", owner_proof(s, "activate", v1)).status_code == 200
    rev1 = s["registry"].catalog()[0]["revision"]
    v2 = binding("2.0.0")
    stage(s, v2, "sandbox-2")
    assert post(s, "activate", owner_proof(s, "activate", v2)).status_code == 200
    assert s["registry"].catalog()[0]["version"] == "2.0.0"

    rollback = owner_proof(s, "rollback", v1)
    s["attestations"].remove((v1.review_digest, "sandbox-1"))
    assert post(s, "rollback", rollback).status_code == 403
    assert s["registry"].catalog()[0]["version"] == "2.0.0"
    s["attestations"].add((v1.review_digest, "sandbox-1"))
    restored = post(s, "rollback", rollback)
    assert restored.status_code == 200, restored.text
    assert restored.json()["revision"] == rev1
    assert post(s, "rollback", rollback).status_code == 403
    req = s["registry"].to_gateway_request(
        "safe_reader", principal_id="local_owner", arguments={"query": "safe"},
    )
    assert req.capability_id == "ReviewedTool"
    assert req.tool_name == "safe_read"  # request only: MCPGateway executes later
    assert post(s, "revoke", owner_proof(s, "revoke", v1)).status_code == 200
    assert s["registry"].catalog() == ()
    with pytest.raises(PermissionError):
        s["registry"].to_gateway_request("safe_reader", principal_id="local_owner")


def test_bad_host_origin_shape_and_attestation_never_consume_owner_proof(governed):
    s = governed
    v1 = binding("1.0.0")
    stage(s, v1, "sandbox-1")
    proof = owner_proof(s, "activate", v1)
    bad = {
        "name": v1.name, "action": "activate", "owner_receipt": proof,
    }
    for headers in (
        {"Host": "evil.invalid", "Origin": "http://localhost:8766"},
        {"Origin": "http://evil.invalid"},
    ):
        assert s["client"].post("/api/activation/version",
            json=bad, headers=headers).status_code == 403
    assert s["client"].post("/api/activation/version",
        json={**bad, "python_source": "__import__('os')"},
        headers={"Origin": "http://localhost:8766"}).status_code == 422
    s["attestations"].clear()
    assert post(s, "activate", proof).status_code == 403
    assert s["registry"].catalog() == ()
    s["attestations"].add((v1.review_digest, "sandbox-1"))
    assert post(s, "activate", proof).status_code == 200
