import asyncio
from unittest.mock import AsyncMock

import pytest

from aura_core.agent.runtime import AgentExecutor, Plan, PlanState, PlanStep, Task
from aura_core.kernel.capabilities import (
    CapabilityCategory,
    CapabilityDefinition,
    CapabilityRegistry,
    ProviderType,
)
from aura_core.kernel.permissions import (
    AuthorizationDecision,
    AuthorizationLevel,
    PermissionEngine,
    PermissionPolicy,
    RiskLevel,
)
from aura_core.kernel.services import (
    ServiceCategory,
    ServiceDefinition,
    ServiceRegistry,
)
from aura_core.mcp.mcp_provider import MCPProvider
from aura_core.mcp.provider import (
    ProviderDefinition,
    ProviderRegistry,
)
from aura_core.mcp.gateway import (
    MCPGateway,
    MCPGatewayRequest,
)
from aura_core.enterprise.runtime_controls import (
    CircuitBreaker, CircuitOpenError, CircuitState, HashChainAuditLedger,
)
from aura_core.enterprise.policy_bundle import (
    PolicyBundle, PolicyEffect, PolicyRule,
)


CAPABILITY_ID = "filesystem.read"
OPERATION_ID = "filesystem.read_file"
TEST_DATA_CAPABILITY_ID = "filesystem.read_test_data"
TEST_DATA_OPERATION_ID = "filesystem.read_test_data"
RESOURCE_SCOPE = r"D:\AURA\workspace"
PROVIDER_ID = "mcp:test"


def make_gateway(
    *,
    provider: object | None = None,
    capability_id: str = CAPABILITY_ID,
    policy_bundle: PolicyBundle | None = None,
) -> tuple[
    MCPGateway,
    PermissionEngine,
    object,
]:
    services = ServiceRegistry()

    service = services.register(
        ServiceDefinition(
            name="mcp-test",
            version="0.1.0",
            provider="mcp",
            category=ServiceCategory.MCP,
        ),
        object(),
    )

    provider_registry = ProviderRegistry(services)

    if provider is None:
        connection = AsyncMock()
        connection.is_connected = True
        provider = MCPProvider(connection)

    provider_registry.register(
        ProviderDefinition(
            provider_id=PROVIDER_ID,
            name="test",
            version="0.1.0",
            service_id=service.service_id,
        ),
        provider,
    )

    capabilities = CapabilityRegistry(services)

    capabilities.register(
        CapabilityDefinition(
            capability_id=capability_id,
            name="Filesystem Read",
            version="1.0.0",
            description="Read a file through MCP.",
            provider_id=PROVIDER_ID,
            provider_type=ProviderType.MCP,
            category=CapabilityCategory.STORAGE,
            required_permissions={"filesystem.read"},
        )
    )

    permissions = PermissionEngine(capabilities, policy_bundle=policy_bundle)

    gateway = MCPGateway(
        capability_registry=capabilities,
        provider_registry=provider_registry,
        permission_engine=permissions,
    )

    return gateway, permissions, provider


def make_request(
    *,
    capability_id: str = CAPABILITY_ID,
    operation_id: str = OPERATION_ID,
    arguments: dict | None = None,
) -> MCPGatewayRequest:
    return MCPGatewayRequest(
        request_id="request-123",
        principal_id="agent:planner",
        capability_id=capability_id,
        operation_id=operation_id,
        resource_scope=RESOURCE_SCOPE,
        risk_level=RiskLevel.LOW,
        tool_name="read_file",
        arguments={"path": r"D:\AURA\workspace\test.txt"} if arguments is None else arguments,
    )


def make_policy(
    decision: AuthorizationDecision,
    *,
    level: AuthorizationLevel = AuthorizationLevel.READ,
    capability_id: str = CAPABILITY_ID,
    operation_id: str = OPERATION_ID,
) -> PermissionPolicy:
    return PermissionPolicy(
        policy_id=f"aura.policy.{decision.value}",
        policy_version="1.0.0",
        principal_id="agent:planner",
        capability_id=capability_id,
        operation_id=operation_id,
        resource_scope=RESOURCE_SCOPE,
        authorization_level=level,
        decision=decision,
    )


def test_gateway_denies_by_default() -> None:
    gateway, _, provider = make_gateway()

    response = asyncio.run(
        gateway.invoke(make_request())
    )

    assert response.decision is AuthorizationDecision.DENY
    assert response.result is None
    assert response.provider_id == PROVIDER_ID
    assert response.tool_name == "read_file"

    provider.connection.call_tool.assert_not_awaited()


def test_gateway_does_not_invoke_provider_when_approval_is_required() -> None:
    gateway, permissions, provider = make_gateway()

    permissions.add_policy(
        make_policy(
            AuthorizationDecision.ALLOW,
            level=AuthorizationLevel.USER_APPROVAL_REQUIRED,
        )
    )

    response = asyncio.run(
        gateway.invoke(make_request())
    )

    assert response.decision is AuthorizationDecision.REQUIRE_APPROVAL
    assert response.result is None
    assert response.provider_id == PROVIDER_ID

    provider.connection.call_tool.assert_not_awaited()


def test_gateway_invokes_allowed_mcp_tool() -> None:
    gateway, permissions, provider = make_gateway()

    expected = {
        "content": [
            {
                "type": "text",
                "text": "hello",
            }
        ]
    }

    provider.connection.call_tool.return_value = expected

    permissions.add_policy(
        make_policy(AuthorizationDecision.ALLOW)
    )

    response = asyncio.run(
        gateway.invoke(make_request())
    )

    assert response.decision is AuthorizationDecision.ALLOW
    assert response.result == expected
    assert response.provider_id == PROVIDER_ID
    assert response.tool_name == "read_file"
    assert response.reason == "MCP tool invocation completed"

    provider.connection.call_tool.assert_awaited_once_with(
        "read_file",
        {"path": r"D:\AURA\workspace\test.txt"},
    )


def test_gateway_explicit_deny_prevents_invocation() -> None:
    gateway, permissions, provider = make_gateway()

    permissions.add_policy(
        make_policy(AuthorizationDecision.ALLOW)
    )
    permissions.add_policy(
        PermissionPolicy(
            policy_id="aura.policy.explicit-deny",
            policy_version="1.0.0",
            principal_id="agent:planner",
            capability_id=CAPABILITY_ID,
            operation_id=OPERATION_ID,
            resource_scope=RESOURCE_SCOPE,
            authorization_level=AuthorizationLevel.DENY,
            decision=AuthorizationDecision.DENY,
            priority=100,
        )
    )

    response = asyncio.run(
        gateway.invoke(make_request())
    )

    assert response.decision is AuthorizationDecision.DENY
    assert response.result is None

    provider.connection.call_tool.assert_not_awaited()


def test_gateway_rejects_non_mcp_provider() -> None:
    gateway, permissions, _ = make_gateway(
        provider=object(),
    )

    permissions.add_policy(
        make_policy(AuthorizationDecision.ALLOW)
    )

    with pytest.raises(
        TypeError,
        match="Resolved provider is not an MCPProvider",
    ):
        asyncio.run(
            gateway.invoke(make_request())
        )


def test_gateway_preserves_tool_arguments() -> None:
    gateway, permissions, provider = make_gateway()

    permissions.add_policy(
        make_policy(AuthorizationDecision.ALLOW)
    )

    request = make_request()

    asyncio.run(
        gateway.invoke(request)
    )

    provider.connection.call_tool.assert_awaited_once_with(
        request.tool_name,
        request.arguments,
    )


@pytest.mark.parametrize(
    "arguments",
    [
        {"path": "other.txt"},
        {"path": r"..\governor-read-test.txt"},
        {"path": r".\governor-read-test.txt"},
        {"path": r"D:\test-data\governor-read-test.txt"},
        {"path": r"C:\temp\governor-read-test.txt"},
        {"path": r"\\server\share\governor-read-test.txt"},
        {"path": "/test-data/governor-read-test.txt"},
        {"path": ""},
        {"path": None},
        {"path": 42},
        {},
    ],
)
def test_executor_rejects_unapproved_test_data_path_before_provider(arguments: dict) -> None:
    gateway, permissions, provider = make_gateway(capability_id=TEST_DATA_CAPABILITY_ID)
    permissions.add_policy(make_policy(
        AuthorizationDecision.ALLOW,
        capability_id=TEST_DATA_CAPABILITY_ID,
        operation_id=TEST_DATA_OPERATION_ID,
    ))
    task = Task("task-path-guard", "agent:planner", "Read test data", RESOURCE_SCOPE)
    plan = Plan("plan-path-guard", task.task_id, (
        PlanStep(
            "step-1", TEST_DATA_CAPABILITY_ID, TEST_DATA_OPERATION_ID,
            "read_file", RiskLevel.LOW, arguments=arguments,
        ),
    ))

    result = asyncio.run(AgentExecutor(gateway).execute(task, plan))

    assert result.state is PlanState.FAILED
    provider.connection.call_tool.assert_not_awaited()


def test_executor_allows_only_exact_test_data_filename_through_gateway() -> None:
    gateway, permissions, provider = make_gateway(capability_id=TEST_DATA_CAPABILITY_ID)
    permissions.add_policy(make_policy(
        AuthorizationDecision.ALLOW,
        capability_id=TEST_DATA_CAPABILITY_ID,
        operation_id=TEST_DATA_OPERATION_ID,
    ))
    task = Task("task-path-allowed", "agent:planner", "Read test data", RESOURCE_SCOPE)
    plan = Plan("plan-path-allowed", task.task_id, (
        PlanStep(
            "step-1", TEST_DATA_CAPABILITY_ID, TEST_DATA_OPERATION_ID,
            "read_file", RiskLevel.LOW, arguments={"path": "governor-read-test.txt"},
        ),
    ))
    provider.connection.call_tool.return_value = {"content": [{"type": "text", "text": "ok"}]}

    result = asyncio.run(AgentExecutor(gateway).execute(task, plan))

    assert result.state is PlanState.SUCCEEDED
    provider.connection.call_tool.assert_awaited_once_with(
        "read_file", {"path": "governor-read-test.txt"}
    )



def test_executor_enforces_shared_step_budget_before_gateway_dispatch() -> None:
    gateway, permissions, provider = make_gateway()
    permissions.add_policy(make_policy(AuthorizationDecision.ALLOW))
    provider.connection.call_tool.return_value = {"content": [{"type": "text", "text": "ok"}]}
    task = Task(
        "task-budget", "agent:planner", "Budget test", RESOURCE_SCOPE,
        max_steps=1, timeout_seconds=5,
    )
    plan = Plan("plan-budget", task.task_id, (
        PlanStep("step-a", CAPABILITY_ID, OPERATION_ID, "read_file", RiskLevel.LOW),
        PlanStep("step-b", CAPABILITY_ID, OPERATION_ID, "read_file", RiskLevel.LOW),
    ))

    result = asyncio.run(AgentExecutor(gateway).execute(task, plan))

    assert result.state is PlanState.FAILED
    assert sum(step.state.value == "succeeded" for step in result.steps) == 1
    provider.connection.call_tool.assert_awaited_once()


def test_gateway_applies_provider_breaker_and_metadata_only_audit() -> None:
    base_gateway, permissions, provider = make_gateway()
    ledger = HashChainAuditLedger()
    breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=60)
    gateway = MCPGateway(
        base_gateway._capability_registry,
        base_gateway._provider_registry,
        permissions,
        circuit_breakers={PROVIDER_ID: breaker},
        audit_ledger=ledger,
    )
    permissions.add_policy(make_policy(AuthorizationDecision.ALLOW))
    provider.connection.call_tool.side_effect = RuntimeError("sensitive provider detail")

    with pytest.raises(RuntimeError, match="sensitive provider detail"):
        asyncio.run(gateway.invoke(make_request()))

    assert breaker.state is CircuitState.OPEN
    records = ledger.snapshot()
    assert len(records) == 1
    assert records[0].outcome == "error"
    assert records[0].reason_code == "provider_call_failed"
    assert "sensitive provider detail" not in repr(records)
    assert ledger.verify()

    with pytest.raises(CircuitOpenError):
        asyncio.run(gateway.invoke(make_request()))

    assert len(ledger.snapshot()) == 2
    assert ledger.verify()



def make_enterprise_bundle(
    effect: PolicyEffect,
    *,
    principal_id: str = "agent:planner",
    capability_id: str = CAPABILITY_ID,
    operation_id: str = OPERATION_ID,
    resource_scope: str = RESOURCE_SCOPE,
) -> PolicyBundle:
    return PolicyBundle(
        version="test-v1",
        rules=(
            PolicyRule(
                rule_id=f"enterprise-{effect.value}",
                principal_id=principal_id,
                capability_id=capability_id,
                operation_id=operation_id,
                resource_scope=resource_scope,
                effect=effect,
            ),
        ),
    )


def test_enterprise_policy_bundle_allow_still_requires_permission_engine_allow() -> None:
    bundle = make_enterprise_bundle(PolicyEffect.ALLOW)
    gateway, _, provider = make_gateway(policy_bundle=bundle)

    response = asyncio.run(gateway.invoke(make_request()))

    # The bundle is an additional gate, not a replacement for the core PermissionPolicy.
    assert response.decision is AuthorizationDecision.DENY
    provider.connection.call_tool.assert_not_awaited()


def test_enterprise_policy_bundle_allow_dispatches_only_after_core_allow() -> None:
    bundle = make_enterprise_bundle(PolicyEffect.ALLOW)
    gateway, permissions, provider = make_gateway(policy_bundle=bundle)
    permissions.add_policy(make_policy(AuthorizationDecision.ALLOW))
    provider.connection.call_tool.return_value = {"content": [{"type": "text", "text": "ok"}]}

    response = asyncio.run(gateway.invoke(make_request()))

    assert response.decision is AuthorizationDecision.ALLOW
    provider.connection.call_tool.assert_awaited_once()


def test_enterprise_policy_bundle_explicit_deny_prevents_provider_dispatch() -> None:
    bundle = make_enterprise_bundle(PolicyEffect.DENY)
    gateway, permissions, provider = make_gateway(policy_bundle=bundle)
    permissions.add_policy(make_policy(AuthorizationDecision.ALLOW))

    response = asyncio.run(gateway.invoke(make_request()))

    assert response.decision is AuthorizationDecision.DENY
    assert "test-v1" in response.reason
    assert "explicit_deny" in response.reason
    provider.connection.call_tool.assert_not_awaited()


def test_enterprise_policy_bundle_missing_or_mismatched_rule_fails_closed() -> None:
    bundle = make_enterprise_bundle(
        PolicyEffect.ALLOW,
        principal_id="some-other-principal",
    )
    gateway, permissions, provider = make_gateway(policy_bundle=bundle)
    permissions.add_policy(make_policy(AuthorizationDecision.ALLOW))

    response = asyncio.run(gateway.invoke(make_request()))

    assert response.decision is AuthorizationDecision.DENY
    assert "no_matching_rule" in response.reason
    provider.connection.call_tool.assert_not_awaited()


def test_enterprise_policy_bundle_approval_required_prevents_provider_dispatch() -> None:
    bundle = make_enterprise_bundle(PolicyEffect.REQUIRE_APPROVAL)
    gateway, permissions, provider = make_gateway(policy_bundle=bundle)
    permissions.add_policy(make_policy(AuthorizationDecision.ALLOW))

    response = asyncio.run(gateway.invoke(make_request()))

    assert response.decision is AuthorizationDecision.REQUIRE_APPROVAL
    assert "approval_required" in response.reason
    provider.connection.call_tool.assert_not_awaited()



def test_gateway_denial_audit_is_metadata_only_and_never_dispatches() -> None:
    base_gateway, permissions, provider = make_gateway()
    ledger = HashChainAuditLedger()
    gateway = MCPGateway(
        base_gateway._capability_registry,
        base_gateway._provider_registry,
        permissions,
        audit_ledger=ledger,
    )
    permissions.add_policy(make_policy(AuthorizationDecision.DENY))
    secret_arguments = {"path": "sensitive/private.txt", "token": "do-not-log"}

    response = asyncio.run(
        gateway.invoke(make_request(arguments=secret_arguments))
    )

    assert response.decision is AuthorizationDecision.DENY
    assert response.result is None
    provider.connection.call_tool.assert_not_awaited()
    records = ledger.snapshot()
    assert len(records) == 1
    assert records[0].outcome == "denied"
    assert records[0].reason_code == "authorization_denied"
    assert "sensitive/private.txt" not in repr(records)
    assert "do-not-log" not in repr(records)
    assert ledger.verify()


def test_gateway_does_not_treat_sibling_resource_scope_as_authorized() -> None:
    gateway, permissions, provider = make_gateway()
    permissions.add_policy(
        PermissionPolicy(
            policy_id="aura.policy.workspace-a",
            policy_version="1.0.0",
            principal_id="agent:planner",
            capability_id=CAPABILITY_ID,
            operation_id=OPERATION_ID,
            resource_scope=r"D:\AURA\workspace-a",
            authorization_level=AuthorizationLevel.READ,
            decision=AuthorizationDecision.ALLOW,
        )
    )

    response = asyncio.run(
        gateway.invoke(make_request())
    )

    assert response.decision is AuthorizationDecision.DENY
    assert response.result is None
    assert "No applicable explicit authorization policy" in response.reason
    provider.connection.call_tool.assert_not_awaited()



@pytest.mark.parametrize(
    ("policy_field", "policy_value"),
    [
        ("principal_id", "agent:other"),
        ("capability_id", "filesystem.write"),
        ("operation_id", "filesystem.write_file"),
        ("resource_scope", r"D:\\AURA\\workspace-sibling"),
    ],
)
def test_authorization_matrix_mismatched_policy_dimension_denies_before_dispatch(
    policy_field: str, policy_value: str,
) -> None:
    gateway, permissions, provider = make_gateway()
    values = {
        "policy_id": f"aura.policy.matrix.{policy_field}",
        "policy_version": "1.0.0",
        "principal_id": "agent:planner",
        "capability_id": CAPABILITY_ID,
        "operation_id": OPERATION_ID,
        "resource_scope": RESOURCE_SCOPE,
        "authorization_level": AuthorizationLevel.READ,
        "decision": AuthorizationDecision.ALLOW,
    }
    values[policy_field] = policy_value
    permissions.add_policy(PermissionPolicy(**values))

    response = asyncio.run(gateway.invoke(make_request()))

    assert response.decision is AuthorizationDecision.DENY
    assert response.result is None
    provider.connection.call_tool.assert_not_awaited()


@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        (AuthorizationDecision.DENY, AuthorizationDecision.DENY),
        (AuthorizationDecision.REQUIRE_APPROVAL, AuthorizationDecision.REQUIRE_APPROVAL),
    ],
)
def test_authorization_matrix_non_allow_decisions_never_dispatch(
    decision: AuthorizationDecision, expected: AuthorizationDecision,
) -> None:
    gateway, permissions, provider = make_gateway()
    permissions.add_policy(make_policy(decision))

    response = asyncio.run(gateway.invoke(make_request()))

    assert response.decision is expected
    assert response.result is None
    provider.connection.call_tool.assert_not_awaited()


def test_authorization_matrix_explicit_allow_dispatches_exact_request() -> None:
    gateway, permissions, provider = make_gateway()
    provider.connection.call_tool.return_value = {"content": [{"type": "text", "text": "ok"}]}
    permissions.add_policy(make_policy(AuthorizationDecision.ALLOW))
    request = make_request(arguments={"path": "approved.txt"})

    response = asyncio.run(gateway.invoke(request))

    assert response.decision is AuthorizationDecision.ALLOW
    provider.connection.call_tool.assert_awaited_once_with("read_file", {"path": "approved.txt"})
