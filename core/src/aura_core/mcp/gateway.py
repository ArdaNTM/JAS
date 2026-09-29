from dataclasses import dataclass
from typing import Any

from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.permissions import (
    AuthorizationDecision,
    AuthorizationRequest,
    PermissionEngine,
    RiskLevel,
)
from aura_core.mcp.mcp_provider import MCPProvider
from aura_core.mcp.provider import ProviderRegistry


@dataclass(frozen=True, slots=True)
class MCPGatewayRequest:
    request_id: str
    principal_id: str
    capability_id: str
    operation_id: str
    resource_scope: str
    risk_level: RiskLevel
    tool_name: str
    arguments: dict[str, Any] | None = None
    session_id: str | None = None
    task_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "request_id",
            "principal_id",
            "capability_id",
            "operation_id",
            "resource_scope",
            "tool_name",
        ):
            if not getattr(self, field_name):
                raise ValueError(
                    f"MCP gateway {field_name} is required"
                )


@dataclass(frozen=True, slots=True)
class MCPGatewayResponse:
    decision: AuthorizationDecision
    result: Any | None
    provider_id: str | None
    tool_name: str
    reason: str


class MCPGateway:
    """Deterministic authorization and dispatch gateway for MCP tools."""

    def __init__(
        self,
        capability_registry: CapabilityRegistry,
        provider_registry: ProviderRegistry,
        permission_engine: PermissionEngine,
    ) -> None:
        self._capability_registry = capability_registry
        self._provider_registry = provider_registry
        self._permission_engine = permission_engine

    async def invoke(
        self,
        request: MCPGatewayRequest,
    ) -> MCPGatewayResponse:
        capability = self._capability_registry.resolve(
            request.capability_id
        )

        authorization = self._permission_engine.authorize(
            AuthorizationRequest(
                request_id=request.request_id,
                principal_id=request.principal_id,
                capability_id=request.capability_id,
                operation_id=request.operation_id,
                resource_scope=request.resource_scope,
                risk_level=request.risk_level,
                session_id=request.session_id,
                task_id=request.task_id,
            )
        )

        if authorization.decision is not AuthorizationDecision.ALLOW:
            return MCPGatewayResponse(
                decision=authorization.decision,
                result=None,
                provider_id=capability.definition.provider_id,
                tool_name=request.tool_name,
                reason=authorization.reason,
            )

        provider = self._provider_registry.resolve(
            capability.definition.provider_id
        )

        if not isinstance(provider, MCPProvider):
            raise TypeError(
                "Resolved provider is not an MCPProvider"
            )

        result = await provider.call_tool(
            request.tool_name,
            request.arguments,
        )

        return MCPGatewayResponse(
            decision=AuthorizationDecision.ALLOW,
            result=result,
            provider_id=capability.definition.provider_id,
            tool_name=request.tool_name,
            reason="MCP tool invocation completed",
        )
