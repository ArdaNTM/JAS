import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aura_core.mcp.connection import MCPConnection
from aura_core.mcp.mcp_provider import MCPProvider


def test_mcp_provider_lists_tools() -> None:
    connection = AsyncMock(spec=MCPConnection)

    connection.is_connected = True
    connection.list_tools.return_value = SimpleNamespace(
        tools=[
            SimpleNamespace(
                name="search",
                description="Search the web",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                },
            ),
            SimpleNamespace(
                name="calculate",
                description=None,
                inputSchema={},
            ),
        ]
    )

    provider = MCPProvider(connection)

    tools = asyncio.run(provider.list_tools())

    assert len(tools) == 2

    assert tools[0].name == "search"
    assert tools[0].description == "Search the web"
    assert tools[0].input_schema["type"] == "object"

    assert tools[1].name == "calculate"
    assert tools[1].input_schema == {}


def test_mcp_provider_calls_tool() -> None:
    connection = AsyncMock(spec=MCPConnection)

    expected = {
        "content": [
            {
                "type": "text",
                "text": "hello",
            }
        ]
    }

    connection.call_tool.return_value = expected

    provider = MCPProvider(connection)

    result = asyncio.run(
        provider.call_tool(
            "search",
            {"query": "AURA"},
        )
    )

    assert result == expected

    connection.call_tool.assert_awaited_once_with(
        "search",
        {"query": "AURA"},
    )


def test_mcp_provider_close_closes_connection() -> None:
    connection = AsyncMock(spec=MCPConnection)

    provider = MCPProvider(connection)

    asyncio.run(provider.close())

    connection.close.assert_awaited_once()


def test_mcp_provider_connection_state() -> None:
    connection = AsyncMock(spec=MCPConnection)
    connection.is_connected = True

    provider = MCPProvider(connection)

    assert provider.connection is connection
    assert provider.is_connected is True
