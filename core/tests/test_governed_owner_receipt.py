"""One-shot signed owner receipt handoff with persistent replay protection."""
import hashlib
import sqlite3
from dataclasses import replace
from datetime import datetime

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aura_core.enterprise.approval_store import ApprovalStatus, SQLiteApprovalStore
from aura_core.evolution.owner_receipt import OwnerReceiptIssuer, SignedOwnerReceipt, DurableOwnerReceiptConsumer
from aura_core.kernel.capabilities import CapabilityRegistry, CapabilityDefinition, CapabilityCategory, ProviderType
from aura_core.kernel.permissions import PermissionEngine, PermissionPolicy, AuthorizationDecision, AuthorizationLevel
from aura_core.kernel.services import ServiceRegistry


def sha(s: bytes) -> str:
    return hashlib.sha256(s).hexdigest()


@pytest.fixture
def scenario(tmp_path):
    digest, policy = sha(b"full-binding"), sha(b"policy")
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    services = ServiceRegistry()
    capabilities = CapabilityRegistry(services)
    capabilities.register(CapabilityDefinition(
        capability_id="GovernedSkillActivation", name="Owner", version="1",
        description="Owner review", provider_id="evolution.guard",
        provider_type=ProviderType.MCP, category=CapabilityCategory.SECURITY,
        tool_name="owner_review", risk_level="critical",
    ))
    permissions = PermissionEngine(capabilities)
    db = tmp_path / "receipts.sqlite"
    sqlite3.connect(db).close()
    db.chmod(0o600)
    with SQLiteApprovalStore(":memory:") as store:
        request = store.create(
            principal_id="local_owner", capability_id="GovernedSkillActivation",
            operation_id="activate", resource_scope="evolution:skill:"+digest,
            request_fingerprint=digest, policy_digest=policy,
        )
        approved = store.decide(
            request.approval_id, expected_version=request.version,
            approver_id="human:local-owner", decision=ApprovalStatus.APPROVED,
        )
        issuer = OwnerReceiptIssuer(
            key_id="protected-owner", private_key=key, policy_digest=policy,
        )
        yield digest, policy, public, key, permissions, db, issuer, approved, request


def consumer(s, public=None):
    digest, policy, pub, key, permissions, db, *_ = s
    return DurableOwnerReceiptConsumer(
        trusted_public_keys={"protected-owner": pub if public is None else public},
        policy_digest=policy, permissions=permissions, ledger_path=db,
    )


def grant(s):
    digest, policy, pub, key, permissions, db, *_ = s
    permissions.add_policy(PermissionPolicy(
        policy_id="jas:owner-permission", policy_version="1",
        principal_id="local_owner", capability_id="GovernedSkillActivation",
        operation_id="activate", resource_scope="evolution:skill:"+digest,
        authorization_level=AuthorizationLevel.USER_APPROVAL_REQUIRED,
        decision=AuthorizationDecision.REQUIRE_APPROVAL,
    ))


def test_signed_owner_receipt_scope_and_issuer_requirements(scenario):
    binding, policy, pub, key, perms, db, issuer, approved, request = scenario
    token = issuer.issue(approved)
    decoded = SignedOwnerReceipt.decode(token)
    assert decoded.claims.binding_digest == binding
    assert decoded.claims.approval_version == approved.version
    assert decoded.claims.operation == "activate"
    for forged in (
        request, replace(approved, status=ApprovalStatus.DENIED),
        replace(approved, approver_id="agent:model"),
        replace(approved, resource_scope="wrong"),
    ):
        with pytest.raises(PermissionError):
            issuer.issue(forged)


def test_denied_without_permission_and_one_use_after_restart(scenario):
    binding, policy, pub, key, perms, db, issuer, approved, request = scenario
    token = issuer.issue(approved)
    verifier = consumer(scenario)
    assert not verifier("local_owner", "activate", binding, token)
    grant(scenario)
    assert not verifier("other", "activate", binding, token)
    assert not verifier("local_owner", "rollback", binding, token)
    assert not verifier("local_owner", "activate", sha(b"wrong-scope"), token)
    assert verifier("local_owner", "activate", binding, token)
    assert not verifier("local_owner", "activate", binding, token)
    verifier.close()
    restarted = consumer(scenario)
    assert not restarted("local_owner", "activate", binding, token)
    restarted.close()


def test_fake_key_or_changed_token_does_not_authorize(scenario):
    binding, policy, pub, key, perms, db, issuer, approved, request = scenario
    grant(scenario)
    attacker = OwnerReceiptIssuer(
        key_id="protected-owner", private_key=Ed25519PrivateKey.generate(),
        policy_digest=policy,
    ).issue(approved)
    verifier = consumer(scenario)
    assert not verifier("local_owner", "activate", binding, attacker)
    token = issuer.issue(approved)
    assert not verifier("local_owner", "activate", binding, token[:-5]+"AAAAA")
    assert verifier("local_owner", "activate", binding, token)
    verifier.close()


def test_expired_token_cannot_be_consumed(scenario, monkeypatch):
    binding, policy, pub, key, perms, db, issuer, approved, request = scenario
    issued = int(datetime.fromisoformat(approved.decided_at).timestamp())
    token = issuer.issue(approved, now=issued)
    grant(scenario)
    verifier = consumer(scenario)
    monkeypatch.setattr("aura_core.evolution.owner_receipt.time.time", lambda: issued+100)
    assert not verifier("local_owner", "activate", binding, token)
    verifier.close()
