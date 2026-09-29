from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client


@dataclass(frozen=True, slots=True)
class MCPToolResult:
    """Result returned by an MCP tool invocation."""

    result: Any


class MCPConnection:
    """Managed client connection to an MCP server.

    Supports MCP stdio and Streamable HTTP transports.
    The underlying ClientSession lifecycle is managed internally.
    """

    def __init__(self) -> None:
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("MCP connection is not initialized")
        return self._session

    @property
    def is_connected(self) -> bool:
        return self._session is not None

    async def connect_stdio(
        self,
        server: StdioServerParameters,
    ) -> None:
        """Connect to an MCP server over stdio."""

        await self._open()

        assert self._stack is not None

        read_stream, write_stream = await self._stack.enter_async_context(
            stdio_client(server)
        )

        session = ClientSession(read_stream, write_stream)
        self._session = await self._stack.enter_async_context(session)

        await self._session.initialize()

    async def connect_http(
        self,
        url: str,
    ) -> None:
        """Connect to an MCP server over Streamable HTTP."""

        await self._open()

        assert self._stack is not None

        read_stream, write_stream = await self._stack.enter_async_context(
            streamable_http_client(url)
        )

        session = ClientSession(read_stream, write_stream)
        self._session = await self._stack.enter_async_context(session)

        await self._session.initialize()

    async def list_tools(self) -> Any:
        """Return the MCP server's available tools."""

        return await self.session.list_tools()

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Invoke an MCP tool."""

        return await self.session.call_tool(
            name,
            arguments=arguments,
        )

    async def close(self) -> None:
        """Close the MCP connection and all managed resources."""

        if self._stack is None:
            return

        stack = self._stack
        self._stack = None
        self._session = None

        await stack.aclose()

    async def _open(self) -> None:
        if self._stack is not None:
            raise RuntimeError("MCP connection is already open")

        self._stack = AsyncExitStack()
