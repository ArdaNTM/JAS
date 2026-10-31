"""One-shot external owner receipts for governed skill version changes.

ApprovalStore records must be CREATED and decided by a separately trusted,
authenticated owner control plane. This adapter never mints/approves receipts.
The PermissionEngine must already know a JAS-owned policy and capability;
otherwise activation fails closed.
"""
from __future__ import annotations

import hmac
from datetime import UTC, datetime
from uuid import uuid4

from aura_core.enterprise.approval_store import ApprovalStatus, SQLiteApprovalStore
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationRequest, PermissionEngine, RiskLevel,
)


class LocalOwnerReceiptAuthority:
    CAPABILITY_ID = "GovernedSkillActivation"

    def __init__(
        self, *, permissions: PermissionEngine, approvals: SQLiteApprovalStore,
        policy_digest: str, approver_id: str = "human:local-owner",
    ) -> None:
        if len(policy_digest) != 64 or not all(c in "0123456789abcdef" for c in policy_digest):
            raise ValueError("A pinned SHA-256 policy digest is required")
        if not approver_id.startswith("human:"):
            raise ValueError("Approval must come from a trusted human control plane")
        self._permissions = permissions
        self._approvals = approvals
        self._policy_digest = policy_digest
        self._approver = approver_id

    def __call__(self, principal_id: str, operation: str, manifest_digest: str, receipt: str) -> bool:
        if principal_id != "local_owner" or operation not in {"activate", "rollback", "revoke"}:
            return False
        if len(manifest_digest) != 64 or len(receipt) > 128:
            return False
        scope = "evolution:skill:" + manifest_digest
        decision = self._permissions.authorize(AuthorizationRequest(
            request_id=str(uuid4()), principal_id=principal_id,
            capability_id=self.CAPABILITY_ID, operation_id=operation,
            resource_scope=scope, risk_level=RiskLevel.CRITICAL,
        ))
        if decision.decision not in {AuthorizationDecision.ALLOW, AuthorizationDecision.REQUIRE_APPROVAL}:
            return False
        record = self._approvals.get(receipt)
        if record is None or record.status is not ApprovalStatus.APPROVED:
            return False
        if record.approver_id != self._approver:
            return False
        if not hmac.compare_digest(record.policy_digest, self._policy_digest):
            return False
        if not hmac.compare_digest(record.request_fingerprint, manifest_digest):
            return False
        try:
            consumed = self._approvals.consume(
                receipt, expected_version=record.version,
                principal_id=principal_id, capability_id=self.CAPABILITY_ID,
                operation_id=operation, resource_scope=scope,
                request_fingerprint=manifest_digest,
                policy_digest=self._policy_digest,
            )
        except (KeyError, ValueError, RuntimeError):
            return False
        return consumed.status is ApprovalStatus.CONSUMED
