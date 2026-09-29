import asyncio
from unittest.mock import AsyncMock, patch

from aura_core.mcp.connection import MCPConnection


def test_stdio_transport_is_initialized() -> None:
    connection = MCPConnection()

    async def run() -> None:
        with patch(
            "aura_core.mcp.connection.stdio_client"
        ) as stdio_client:
            transport = AsyncMock()
            transport.__aenter__.return_value = (
                object(),
                object(),
            )
            stdio_client.return_value = transport

            session = AsyncMock()
            session.__aenter__.return_value = session
            session.initialize.return_value = object()

            with patch(
                "aura_core.mcp.connection.ClientSession",
                return_value=session,
            ):
                from mcp.client.stdio import StdioServerParameters

                server = StdioServerParameters(
                    command="test-server",
                )

                await connection.connect_stdio(server)

                stdio_client.assert_called_once_with(server)
                session.initialize.assert_awaited_once()
                assert connection.is_connected is True

        await connection.close()

    asyncio.run(run())


def test_http_transport_is_initialized() -> None:
    connection = MCPConnection()

    async def run() -> None:
        with patch(
            "aura_core.mcp.connection.streamable_http_client"
        ) as http_client:
            transport = AsyncMock()
            transport.__aenter__.return_value = (
                object(),
                object(),
            )
            http_client.return_value = transport

            session = AsyncMock()
            session.__aenter__.return_value = session
            session.initialize.return_value = object()

            with patch(
                "aura_core.mcp.connection.ClientSession",
                return_value=session,
            ):
                url = "http://127.0.0.1:8000/mcp"

                await connection.connect_http(url)

                http_client.assert_called_once_with(url)
                session.initialize.assert_awaited_once()
                assert connection.is_connected is True

        await connection.close()

    asyncio.run(run())
