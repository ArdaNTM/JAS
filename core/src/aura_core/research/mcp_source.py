from __future__ import annotations

from typing import Any

from aura_core.kernel.permissions import RiskLevel
from aura_core.mcp.gateway import MCPGatewayRequest
from aura_core.kernel.permissions import AuthorizationDecision
from .evidence import collect_search_evidence


class MCPResearchSource:
    def __init__(
        self,
        gateway: Any,
        tool_spec: Any,
    ) -> None:
        self.gateway = gateway
        self.tool_spec = tool_spec

    async def search(
        self,
        *,
        principal_id: str,
        query: str,
        resource_scope: str,
        risk_level: RiskLevel,
        task_id: str,
    ) -> Any:
        request = MCPGatewayRequest(
            request_id=f"{task_id}:search",
            principal_id=principal_id,
            capability_id=(
                self.tool_spec.search_capability_id
            ),
            operation_id=(
                self.tool_spec.search_operation_id
            ),
            resource_scope=resource_scope,
            risk_level=risk_level,
            tool_name=(
                self.tool_spec.search_tool_name
            ),
            arguments={
                "query": query,
            },
            session_id=f"research:{task_id}",
            task_id=task_id,
        )

        return await self.gateway.invoke(
            request
        )

    async def search_with_evidence(
        self, *, principal_id: str, query: str, resource_scope: str,
        risk_level: RiskLevel, task_id: str, limit: int = 10,
    ) -> tuple[Any, tuple[dict[str, Any], ...]]:
        """Preserve the Gateway decision; decorate only authorized results.

        This does not issue additional tool requests or alter search policies.
        """
        if type(limit) is not int or not 1 <= limit <= 25:
            raise ValueError("source evidence limit must be 1..25")
        response = await self.search(
            principal_id=principal_id, query=query,
            resource_scope=resource_scope, risk_level=risk_level, task_id=task_id,
        )
        if response.decision is not AuthorizationDecision.ALLOW:
            return response, ()
        return response, collect_search_evidence(response.result, limit=limit)

    async def fetch(
        self,
        *,
        principal_id: str,
        uri: str,
        resource_scope: str,
        risk_level: RiskLevel,
        task_id: str,
    ) -> Any:
        request = MCPGatewayRequest(
            request_id=f"{task_id}:fetch",
            principal_id=principal_id,
            capability_id=(
                self.tool_spec.fetch_capability_id
            ),
            operation_id=(
                self.tool_spec.fetch_operation_id
            ),
            resource_scope=resource_scope,
            risk_level=risk_level,
            tool_name=(
                self.tool_spec.fetch_tool_name
            ),
            arguments={
                "url": uri,
            },
            session_id=f"research:{task_id}",
            task_id=task_id,
        )

        return await self.gateway.invoke(
            request
        )
