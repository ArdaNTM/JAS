"""External trust-boundary tests for owner approval receipts."""
import hashlib

from aura_core.enterprise.approval_store import SQLiteApprovalStore, ApprovalStatus
from aura_core.evolution.owner_authority import LocalOwnerReceiptAuthority
from aura_core.kernel.capabilities import CapabilityRegistry, CapabilityDefinition, CapabilityCategory, ProviderType
from aura_core.kernel.permissions import PermissionEngine, PermissionPolicy, AuthorizationDecision, AuthorizationLevel
from aura_core.kernel.services import ServiceRegistry


def _identity():
    services = ServiceRegistry()
    caps = CapabilityRegistry(services)
    caps.register(CapabilityDefinition(
        capability_id="GovernedSkillActivation", name="Owner governance", version="1",
        description="Human-approved review receipts only", provider_id="evolution.guard",
        provider_type=ProviderType.MCP, category=CapabilityCategory.SECURITY,
        tool_name="owner_review", risk_level="critical",
    ))
    return caps


def test_owner_authority_requires_policy_human_decision_and_consumes_once():
    digest = hashlib.sha256(b"reviewed manifest").hexdigest()
    policy_digest = hashlib.sha256(b"pinned policy").hexdigest()
    scope = "evolution:skill:" + digest
    caps = _identity()
    permissions = PermissionEngine(caps)
    with SQLiteApprovalStore(":memory:") as approvals:
        record = approvals.create(
            principal_id="local_owner", capability_id="GovernedSkillActivation",
            operation_id="activate", resource_scope=scope,
            request_fingerprint=digest, policy_digest=policy_digest,
            ttl_seconds=900,
        )
        approved = approvals.decide(
            record.approval_id, expected_version=record.version,
            approver_id="human:local-owner", decision=ApprovalStatus.APPROVED,
        )
        authority = LocalOwnerReceiptAuthority(
            permissions=permissions, approvals=approvals, policy_digest=policy_digest,
        )
        # An owner-approved record alone cannot defeat PermissionEngine default-deny.
        assert not authority("local_owner", "activate", digest, approved.approval_id)
        permissions.add_policy(PermissionPolicy(
            policy_id="jas:owner-evolution", policy_version="1.0.0",
            principal_id="local_owner", capability_id="GovernedSkillActivation",
            operation_id="activate", resource_scope=scope,
            authorization_level=AuthorizationLevel.USER_APPROVAL_REQUIRED,
            decision=AuthorizationDecision.REQUIRE_APPROVAL,
        ))
        assert not authority("other", "activate", digest, approved.approval_id)
        assert not authority("local_owner", "rollback", digest, approved.approval_id)
        assert authority("local_owner", "activate", digest, approved.approval_id)
        assert approvals.get(approved.approval_id).status is ApprovalStatus.CONSUMED
        assert not authority("local_owner", "activate", digest, approved.approval_id)


def test_wrong_human_approver_cannot_grant_activation():
    digest = hashlib.sha256(b"skill").hexdigest()
    pinned = hashlib.sha256(b"policy").hexdigest()
    scope = "evolution:skill:" + digest
    permissions = PermissionEngine(_identity())
    permissions.add_policy(PermissionPolicy(
        policy_id="owner-gate", policy_version="1",
        principal_id="local_owner", capability_id="GovernedSkillActivation",
        operation_id="activate", resource_scope=scope,
        authorization_level=AuthorizationLevel.USER_APPROVAL_REQUIRED,
        decision=AuthorizationDecision.REQUIRE_APPROVAL,
    ))
    with SQLiteApprovalStore(":memory:") as store:
        record = store.create(
            principal_id="local_owner", capability_id="GovernedSkillActivation",
            operation_id="activate", resource_scope=scope,
            request_fingerprint=digest, policy_digest=pinned,
        )
        approved = store.decide(
            record.approval_id, expected_version=1,
            approver_id="model:automated", decision=ApprovalStatus.APPROVED,
        )
        authority = LocalOwnerReceiptAuthority(
            permissions=permissions, approvals=store, policy_digest=pinned,
        )
        assert not authority("local_owner", "activate", digest, approved.approval_id)
