import asyncio
from unittest.mock import AsyncMock

import pytest

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


CAPABILITY_ID = "filesystem.read"
OPERATION_ID = "filesystem.read_file"
RESOURCE_SCOPE = r"D:\AURA\workspace"
PROVIDER_ID = "mcp:test"


def make_gateway(
    *,
    provider: object | None = None,
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
            capability_id=CAPABILITY_ID,
            name="Filesystem Read",
            version="1.0.0",
            description="Read a file through MCP.",
            provider_id=PROVIDER_ID,
            provider_type=ProviderType.MCP,
            category=CapabilityCategory.STORAGE,
            required_permissions={"filesystem.read"},
        )
    )

    permissions = PermissionEngine(capabilities)

    gateway = MCPGateway(
        capability_registry=capabilities,
        provider_registry=provider_registry,
        permission_engine=permissions,
    )

    return gateway, permissions, provider


def make_request() -> MCPGatewayRequest:
    return MCPGatewayRequest(
        request_id="request-123",
        principal_id="agent:planner",
        capability_id=CAPABILITY_ID,
        operation_id=OPERATION_ID,
        resource_scope=RESOURCE_SCOPE,
        risk_level=RiskLevel.LOW,
        tool_name="read_file",
        arguments={"path": r"D:\AURA\workspace\test.txt"},
    )


def make_policy(
    decision: AuthorizationDecision,
    *,
    level: AuthorizationLevel = AuthorizationLevel.READ,
) -> PermissionPolicy:
    return PermissionPolicy(
        policy_id=f"aura.policy.{decision.value}",
        policy_version="1.0.0",
        principal_id="agent:planner",
        capability_id=CAPABILITY_ID,
        operation_id=OPERATION_ID,
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
