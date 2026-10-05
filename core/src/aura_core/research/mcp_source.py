from __future__ import annotations

from typing import Any

from aura_core.kernel.permissions import RiskLevel
from aura_core.mcp.gateway import MCPGatewayRequest


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
