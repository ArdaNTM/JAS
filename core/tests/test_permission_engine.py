import asyncio
from datetime import UTC, datetime, timedelta

from aura_core.kernel.capabilities import (
    CapabilityCategory,
    CapabilityDefinition,
    CapabilityRegistry,
    ProviderType,
)
from aura_core.kernel.events import EventBus
from aura_core.kernel.permissions import (
    AuthorizationDecision,
    AuthorizationLevel,
    AuthorizationRequest,
    PermissionEngine,
    PermissionPolicy,
    RiskLevel,
)
from aura_core.kernel.services import (
    ServiceCategory,
    ServiceDefinition,
    ServiceRegistry,
)


CAPABILITY_ID = "filesystem.write"
OPERATION_ID = "filesystem.write_file"
RESOURCE_SCOPE = "D:\\AURA\\workspace"


def make_engine(event_bus: EventBus | None = None) -> PermissionEngine:
    services = ServiceRegistry()
    provider = services.register(
        ServiceDefinition(
            name="filesystem",
            version="1.0.0",
            provider="aura",
            category=ServiceCategory.CORE,
        ),
        object(),
    )
    capabilities = CapabilityRegistry(services)
    capabilities.register(
        CapabilityDefinition(
            capability_id=CAPABILITY_ID,
            name="Filesystem Write",
            version="1.0.0",
            description="Write a file in an authorized scope.",
            provider_id=provider.service_id,
            provider_type=ProviderType.SERVICE,
            category=CapabilityCategory.STORAGE,
            required_permissions={"filesystem.write"},
        )
    )
    return PermissionEngine(capabilities, event_bus=event_bus)


def make_request(resource_scope: str = RESOURCE_SCOPE) -> AuthorizationRequest:
    return AuthorizationRequest(
        request_id="request-123",
        principal_id="agent:planner",
        capability_id=CAPABILITY_ID,
        operation_id=OPERATION_ID,
        resource_scope=resource_scope,
        risk_level=RiskLevel.MEDIUM,
    )


def make_policy(
    decision: AuthorizationDecision,
    *,
    policy_id: str = "aura.policy.filesystem.write",
    priority: int = 0,
    level: AuthorizationLevel = AuthorizationLevel.WRITE,
    expires_at: datetime | None = None,
) -> PermissionPolicy:
    return PermissionPolicy(
        policy_id=policy_id,
        policy_version="1.0.0",
        principal_id="agent:planner",
        capability_id=CAPABILITY_ID,
        operation_id=OPERATION_ID,
        resource_scope=RESOURCE_SCOPE,
        authorization_level=level,
        decision=decision,
        priority=priority,
        expires_at=expires_at,
    )


def test_engine_denies_by_default_and_records_audit() -> None:
    engine = make_engine()

    decision = engine.authorize(make_request())

    assert decision.decision is AuthorizationDecision.DENY
    assert decision.policy_id is None
    assert len(engine.audit_records()) == 1


def test_engine_allows_explicit_policy_only_within_scope() -> None:
    engine = make_engine()
    engine.add_policy(make_policy(AuthorizationDecision.ALLOW))

    allowed = engine.authorize(make_request("D:\\AURA\\workspace\\notes.txt"))
    denied = engine.authorize(make_request("D:\\AURA\\outside.txt"))

    assert allowed.decision is AuthorizationDecision.ALLOW
    assert allowed.policy_id == "aura.policy.filesystem.write"
    assert denied.decision is AuthorizationDecision.DENY


def test_explicit_deny_overrides_allow_deterministically() -> None:
    engine = make_engine()
    engine.add_policy(make_policy(AuthorizationDecision.ALLOW, priority=100))
    engine.add_policy(
        make_policy(
            AuthorizationDecision.DENY,
            policy_id="aura.policy.filesystem.deny",
            priority=1,
        )
    )

    decision = engine.authorize(make_request())

    assert decision.decision is AuthorizationDecision.DENY
    assert decision.policy_id == "aura.policy.filesystem.deny"


def test_engine_requires_approval_when_policy_requires_it() -> None:
    engine = make_engine()
    engine.add_policy(
        make_policy(
            AuthorizationDecision.ALLOW,
            level=AuthorizationLevel.USER_APPROVAL_REQUIRED,
        )
    )

    decision = engine.authorize(make_request())

    assert decision.decision is AuthorizationDecision.REQUIRE_APPROVAL


def test_expired_and_revoked_policies_do_not_authorize() -> None:
    engine = make_engine()
    engine.add_policy(
        make_policy(
            AuthorizationDecision.ALLOW,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )

    assert engine.authorize(make_request()).decision is AuthorizationDecision.DENY

    engine = make_engine()
    policy = make_policy(AuthorizationDecision.ALLOW)
    engine.add_policy(policy)
    engine.revoke_policy(policy.policy_id)
    assert engine.authorize(make_request()).decision is AuthorizationDecision.DENY


def test_denial_publishes_permission_denied_event() -> None:
    event_bus = EventBus()
    received: list[str] = []
    event_bus.subscribe("PermissionDenied", lambda event: received.append(event.event_type))
    engine = make_engine(event_bus)

    engine.authorize(make_request())

    assert asyncio.run(event_bus.dispatch_once()) is True
    assert received == ["PermissionDenied"]
