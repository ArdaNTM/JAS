from dataclasses import dataclass
from typing import Any

from aura_core.mcp.connection import MCPConnection


@dataclass(frozen=True, slots=True)
class MCPTool:
    name: str
    description: str | None
    input_schema: dict[str, Any]


class MCPProvider:
    """Provider adapter for an MCP server connection."""

    def __init__(
        self,
        connection: MCPConnection,
    ) -> None:
        self._connection = connection

    @property
    def connection(self) -> MCPConnection:
        return self._connection

    @property
    def is_connected(self) -> bool:
        return self._connection.is_connected

    async def list_tools(self) -> tuple[MCPTool, ...]:
        """Discover tools exposed by the connected MCP server."""

        result = await self._connection.list_tools()

        tools = getattr(result, "tools", None)

        if tools is None:
            raise RuntimeError(
                "MCP server returned an invalid tool listing"
            )

        return tuple(
            MCPTool(
                name=tool.name,
                description=getattr(tool, "description", None),
                input_schema=dict(
                    getattr(tool, "inputSchema", {})
                    or {}
                ),
            )
            for tool in tools
        )

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Invoke a tool exposed by the MCP server."""

        return await self._connection.call_tool(
            name,
            arguments,
        )

    async def close(self) -> None:
        """Close the underlying MCP connection."""

        await self._connection.close()
