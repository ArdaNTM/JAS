import asyncio

import pytest

from aura_core.kernel.events import EventBus
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.tool_registry import MCPToolRegistry


def make_tool(name: str) -> MCPTool:
    return MCPTool(
        name=name,
        description=f"Test tool {name}",
        input_schema={
            "type": "object",
            "properties": {},
        },
    )


def test_tool_registration() -> None:
    registry = MCPToolRegistry()

    record = registry.register(
        "mcp:test",
        make_tool("read_file"),
    )

    assert record.provider_id == "mcp:test"
    assert record.tool.name == "read_file"
    assert record.available is True


def test_tool_resolve() -> None:
    registry = MCPToolRegistry()

    registry.register(
        "mcp:test",
        make_tool("read_file"),
    )

    record = registry.resolve(
        "mcp:test",
        "read_file",
    )

    assert record.tool.name == "read_file"


def test_unknown_tool_is_rejected() -> None:
    registry = MCPToolRegistry()

    with pytest.raises(KeyError, match="Unknown MCP tool"):
        registry.resolve(
            "mcp:test",
            "missing",
        )


def test_duplicate_tool_is_rejected() -> None:
    registry = MCPToolRegistry()

    registry.register(
        "mcp:test",
        make_tool("read_file"),
    )

    with pytest.raises(ValueError, match="already registered"):
        registry.register(
            "mcp:test",
            make_tool("read_file"),
        )


def test_same_tool_name_can_exist_on_different_providers() -> None:
    registry = MCPToolRegistry()

    first = registry.register(
        "mcp:filesystem",
        make_tool("read_file"),
    )

    second = registry.register(
        "mcp:documents",
        make_tool("read_file"),
    )

    assert first.tool.name == "read_file"
    assert second.tool.name == "read_file"

    assert registry.find("read_file") == (
        second,
        first,
    )


def test_tools_for_provider_are_sorted() -> None:
    registry = MCPToolRegistry()

    registry.register_many(
        "mcp:test",
        (
            make_tool("write_file"),
            make_tool("read_file"),
            make_tool("delete_file"),
        ),
    )

    tools = registry.tools_for_provider("mcp:test")

    assert [record.tool.name for record in tools] == [
        "delete_file",
        "read_file",
        "write_file",
    ]


def test_register_many() -> None:
    registry = MCPToolRegistry()

    records = registry.register_many(
        "mcp:test",
        (
            make_tool("tool_a"),
            make_tool("tool_b"),
        ),
    )

    assert len(records) == 2
    assert len(registry.records()) == 2


def test_unregister_tool() -> None:
    registry = MCPToolRegistry()

    registry.register(
        "mcp:test",
        make_tool("read_file"),
    )

    retired = registry.unregister(
        "mcp:test",
        "read_file",
    )

    assert retired.available is False

    with pytest.raises(KeyError):
        registry.resolve(
            "mcp:test",
            "read_file",
        )


def test_unregister_provider() -> None:
    registry = MCPToolRegistry()

    registry.register_many(
        "mcp:test",
        (
            make_tool("read_file"),
            make_tool("write_file"),
        ),
    )

    retired = registry.unregister_provider("mcp:test")

    assert len(retired) == 2
    assert registry.tools_for_provider("mcp:test") == ()


def test_duplicate_batch_is_rejected_atomically() -> None:
    registry = MCPToolRegistry()

    registry.register(
        "mcp:test",
        make_tool("existing"),
    )

    with pytest.raises(ValueError):
        registry.register_many(
            "mcp:test",
            (
                make_tool("new_tool"),
                make_tool("existing"),
            ),
        )

    assert [
        record.tool.name
        for record in registry.tools_for_provider("mcp:test")
    ] == ["existing"]


def test_registration_publishes_events() -> None:
    event_bus = EventBus()
    received = []

    event_bus.subscribe(
        "MCPToolRegistered",
        lambda event: received.append(event),
    )

    registry = MCPToolRegistry(event_bus)

    registry.register(
        "mcp:test",
        make_tool("read_file"),
    )

    assert asyncio.run(event_bus.dispatch_once()) is True

    assert len(received) == 1
    assert received[0].event_type == "MCPToolRegistered"
    assert received[0].payload["provider_id"] == "mcp:test"
    assert received[0].payload["tool_name"] == "read_file"


def test_removal_publishes_event() -> None:
    event_bus = EventBus()
    received = []

    event_bus.subscribe(
        "MCPToolRemoved",
        lambda event: received.append(event),
    )

    registry = MCPToolRegistry(event_bus)

    registry.register(
        "mcp:test",
        make_tool("read_file"),
    )

    registry.unregister(
        "mcp:test",
        "read_file",
    )

    assert asyncio.run(event_bus.dispatch_once()) is False
    assert asyncio.run(event_bus.dispatch_once()) is True

    assert len(received) == 1
    assert received[0].payload["provider_id"] == "mcp:test"
    assert received[0].payload["tool_name"] == "read_file"
    assert received[0].payload["available"] is False
