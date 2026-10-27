from dataclasses import dataclass
from typing import Any

from aura_core.mcp.connection import MCPConnection


@dataclass(frozen=True, slots=True)
class MCPTool:
    name: str
    description: str | None
    input_schema: dict[str, Any]


def _extract_input_schema(tool: Any) -> dict[str, Any]:
    """Read MCP tool schemas across SDK/Pydantic field naming conventions."""

    schema = getattr(tool, "input_schema", None)
    if schema is None:
        schema = getattr(tool, "inputSchema", None)

    if schema is None:
        model_dump = getattr(tool, "model_dump", None)
        if callable(model_dump):
            # MCP SDK models may expose aliased JSON fields only in the dump.
            for by_alias in (True, False):
                dumped = model_dump(by_alias=by_alias)
                if isinstance(dumped, dict):
                    schema = dumped.get("inputSchema", dumped.get("input_schema"))
                    if schema is not None:
                        break

    if schema is None:
        legacy_dict = getattr(tool, "dict", None)
        if callable(legacy_dict):
            for by_alias in (True, False):
                dumped = legacy_dict(by_alias=by_alias)
                if isinstance(dumped, dict):
                    schema = dumped.get("inputSchema", dumped.get("input_schema"))
                    if schema is not None:
                        break

    if schema is None:
        return {}
    if not isinstance(schema, dict):
        raise RuntimeError(
            f"MCP tool {getattr(tool, 'name', '<unknown>')!r} returned "
            f"a non-dictionary input schema: {type(schema).__name__}"
        )
    return dict(schema)


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
                input_schema=_extract_input_schema(tool),
            )
            for tool in tools
        )

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Invoke a tool exposed by an MCP server."""

        return await self._connection.call_tool(
            name,
            arguments,
        )

    async def close(self) -> None:
        """Close the underlying MCP connection."""

        await self._connection.close()
