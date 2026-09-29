from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from threading import RLock
from typing import Mapping

from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.events import EventBus, KernelEvent


class AuthorizationLevel(IntEnum):
    DENY = 0
    READ = 1
    WRITE = 2
    EXECUTE = 3
    PRIVILEGED = 4
    USER_APPROVAL_REQUIRED = 5


class RiskLevel(StrEnum):
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AuthorizationDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    DEFER = "defer"


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    request_id: str
    principal_id: str
    capability_id: str
    operation_id: str
    resource_scope: str
    risk_level: RiskLevel
    session_id: str | None = None
    task_id: str | None = None
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    def __post_init__(self) -> None:
        for field_name in (
            "request_id",
            "principal_id",
            "capability_id",
            "operation_id",
            "resource_scope",
        ):
            if not getattr(self, field_name):
                raise ValueError(f"Authorization {field_name} is required")


@dataclass(frozen=True, slots=True)
class PermissionPolicy:
    policy_id: str
    policy_version: str
    principal_id: str
    capability_id: str
    operation_id: str
    resource_scope: str
    authorization_level: AuthorizationLevel
    decision: AuthorizationDecision
    priority: int = 0
    expires_at: datetime | None = None
    revoked: bool = False
    conditions: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "policy_id",
            "policy_version",
            "principal_id",
            "capability_id",
            "operation_id",
            "resource_scope",
        ):
            if not getattr(self, field_name):
                raise ValueError(f"Policy {field_name} is required")


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    decision: AuthorizationDecision
    reason: str
    policy_id: str | None
    policy_version: str | None
    principal_id: str
    capability_id: str
    operation_id: str
    resource_scope: str
    timestamp: datetime
    expires_at: datetime | None
    risk_level: RiskLevel


@dataclass(frozen=True, slots=True)
class PermissionAuditRecord:
    request: AuthorizationRequest
    decision: PermissionDecision


class PermissionEngine:
    """Deterministic default-deny authorization service for the Kernel."""

    def __init__(
        self,
        capability_registry: CapabilityRegistry,
        event_bus: EventBus | None = None,
    ) -> None:
        self._capability_registry = capability_registry
        self._event_bus = event_bus
        self._policies: dict[str, PermissionPolicy] = {}
        self._audit_records: list[PermissionAuditRecord] = []
        self._lock = RLock()

    def add_policy(self, policy: PermissionPolicy) -> None:
        with self._lock:
            if policy.policy_id in self._policies:
                raise ValueError(f"Policy already exists: {policy.policy_id}")
            self._policies[policy.policy_id] = policy

    def revoke_policy(self, policy_id: str) -> None:
        with self._lock:
            try:
                policy = self._policies[policy_id]
            except KeyError as exc:
                raise KeyError(f"Unknown policy: {policy_id}") from exc
            self._policies[policy_id] = replace(policy, revoked=True)

    def authorize(
        self,
        request: AuthorizationRequest,
    ) -> PermissionDecision:
        try:
            self._capability_registry.resolve(request.capability_id)
        except LookupError:
            return self._record(
                request,
                AuthorizationDecision.DENY,
                "Requested capability has no available provider",
            )

        matching = self._matching_policies(request)
        if not matching:
            return self._record(
                request,
                AuthorizationDecision.DENY,
                "No applicable explicit authorization policy",
            )

        deny = next(
            (
                policy
                for policy in matching
                if policy.decision is AuthorizationDecision.DENY
            ),
            None,
        )
        if deny is not None:
            return self._record(
                request,
                AuthorizationDecision.DENY,
                "Explicit deny policy matched",
                deny,
            )

        approval = next(
            (
                policy
                for policy in matching
                if policy.decision is AuthorizationDecision.REQUIRE_APPROVAL
                or policy.authorization_level
                is AuthorizationLevel.USER_APPROVAL_REQUIRED
            ),
            None,
        )
        if approval is not None:
            return self._record(
                request,
                AuthorizationDecision.REQUIRE_APPROVAL,
                "Explicit user approval is required",
                approval,
            )

        allow = next(
            (
                policy
                for policy in matching
                if policy.decision is AuthorizationDecision.ALLOW
            ),
            None,
        )
        if allow is not None:
            return self._record(
                request,
                AuthorizationDecision.ALLOW,
                "Explicit allow policy matched",
                allow,
            )

        return self._record(
            request,
            AuthorizationDecision.DENY,
            "No applicable explicit allow policy",
        )

    def audit_records(self) -> tuple[PermissionAuditRecord, ...]:
        with self._lock:
            return tuple(self._audit_records)

    def _matching_policies(
        self,
        request: AuthorizationRequest,
    ) -> tuple[PermissionPolicy, ...]:
        now = request.timestamp
        with self._lock:
            policies = tuple(self._policies.values())

        matching = [
            policy
            for policy in policies
            if not policy.revoked
            and (policy.expires_at is None or policy.expires_at > now)
            and not policy.conditions
            and policy.principal_id == request.principal_id
            and policy.capability_id == request.capability_id
            and policy.operation_id == request.operation_id
            and self._scope_matches(
                policy.resource_scope,
                request.resource_scope,
            )
        ]
        return tuple(
            sorted(matching, key=lambda policy: (-policy.priority, policy.policy_id))
        )

    @staticmethod
    def _scope_matches(policy_scope: str, requested_scope: str) -> bool:
        normalized_policy = policy_scope.rstrip("\\/")
        normalized_request = requested_scope.rstrip("\\/")
        return (
            normalized_request == normalized_policy
            or normalized_request.startswith(normalized_policy + "\\")
            or normalized_request.startswith(normalized_policy + "/")
        )

    def _record(
        self,
        request: AuthorizationRequest,
        decision: AuthorizationDecision,
        reason: str,
        policy: PermissionPolicy | None = None,
    ) -> PermissionDecision:
        result = PermissionDecision(
            decision=decision,
            reason=reason,
            policy_id=policy.policy_id if policy else None,
            policy_version=policy.policy_version if policy else None,
            principal_id=request.principal_id,
            capability_id=request.capability_id,
            operation_id=request.operation_id,
            resource_scope=request.resource_scope,
            timestamp=datetime.now(UTC),
            expires_at=policy.expires_at if policy else None,
            risk_level=request.risk_level,
        )
        with self._lock:
            self._audit_records.append(
                PermissionAuditRecord(request=request, decision=result)
            )

        if result.decision is AuthorizationDecision.DENY:
            self._publish("PermissionDenied", request, result)
        elif result.decision is AuthorizationDecision.REQUIRE_APPROVAL:
            self._publish("PermissionApprovalRequired", request, result)

        return result

    def _publish(
        self,
        event_type: str,
        request: AuthorizationRequest,
        decision: PermissionDecision,
    ) -> None:
        if self._event_bus is None:
            return

        self._event_bus.publish(
            KernelEvent(
                event_type=event_type,
                source_component="permission_engine",
                correlation_id=request.request_id,
                session_id=request.session_id,
                payload={
                    "principal_id": request.principal_id,
                    "capability_id": request.capability_id,
                    "operation_id": request.operation_id,
                    "decision": decision.decision,
                    "reason": decision.reason,
                },
            )
        )
