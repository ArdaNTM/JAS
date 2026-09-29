import asyncio

import pytest

from aura_core.discovery.service import ToolDiscoveryRequest, ToolDiscoveryService, ToolSelectionService
from aura_core.kernel.capabilities import CapabilityCategory, CapabilityDefinition, CapabilityRegistry, LatencyClass, ProviderType, QualityClass
from aura_core.kernel.events import EventBus
from aura_core.kernel.services import ServiceRegistry
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.tool_registry import MCPToolRegistry

CAPABILITY = "filesystem.read"


def tool(name: str) -> MCPTool:
    return MCPTool(name=name, description=name, input_schema={"type": "object"})


def make_discovery(event_bus: EventBus | None = None) -> tuple[ToolDiscoveryService, CapabilityRegistry, MCPToolRegistry]:
    services = ServiceRegistry()
    capabilities = CapabilityRegistry(services)
    tools = MCPToolRegistry()
    return ToolDiscoveryService(capabilities, tools, event_bus), capabilities, tools


def add_capability(registry: CapabilityRegistry, provider_id: str, *, priority: int = 0, quality: QualityClass = QualityClass.STANDARD, latency: LatencyClass = LatencyClass.MEDIUM) -> None:
    registry.register(CapabilityDefinition(
        capability_id=CAPABILITY, name="Read", version="1", description="Read files",
        provider_id=provider_id, provider_type=ProviderType.MCP,
        category=CapabilityCategory.STORAGE, priority=priority,
        quality_class=quality, latency_class=latency,
    ))


def request(**kwargs: object) -> ToolDiscoveryRequest:
    return ToolDiscoveryRequest(capability_id=CAPABILITY, operation_id="filesystem.read_file", **kwargs)


def test_discovery_joins_available_mcp_capabilities_with_registered_tools() -> None:
    discovery, capabilities, tools = make_discovery()
    add_capability(capabilities, "mcp:filesystem")
    tools.register_many("mcp:filesystem", (tool("read_file"), tool("stat_file")))
    assert [(item.provider_id, item.tool_name) for item in discovery.discover(request())] == [("mcp:filesystem", "read_file"), ("mcp:filesystem", "stat_file")]


def test_discovery_filters_requested_tool_names() -> None:
    discovery, capabilities, tools = make_discovery()
    add_capability(capabilities, "mcp:filesystem")
    tools.register_many("mcp:filesystem", (tool("read_file"), tool("stat_file")))
    assert [item.tool_name for item in discovery.discover(request(requested_tool_names={"stat_file"}))] == ["stat_file"]


def test_discovery_excludes_unhealthy_capability_provider() -> None:
    discovery, capabilities, tools = make_discovery()
    add_capability(capabilities, "mcp:filesystem")
    tools.register("mcp:filesystem", tool("read_file"))
    capabilities.update_health(CAPABILITY, "mcp:filesystem", available=True, healthy=False)
    assert discovery.discover(request()) == ()


def test_selection_is_deterministic_over_priority_quality_latency_and_ids() -> None:
    discovery, capabilities, tools = make_discovery()
    add_capability(capabilities, "mcp:z", priority=10, quality=QualityClass.BASIC)
    add_capability(capabilities, "mcp:a", priority=10, quality=QualityClass.HIGH, latency=LatencyClass.HIGH)
    add_capability(capabilities, "mcp:b", priority=10, quality=QualityClass.HIGH, latency=LatencyClass.LOW)
    for provider in ("mcp:z", "mcp:a", "mcp:b"):
        tools.register(provider, tool("read_file"))
    assert ToolSelectionService().select(discovery.discover(request())).provider_id == "mcp:b"


def test_selection_rejects_an_empty_candidate_set() -> None:
    with pytest.raises(LookupError, match="No eligible MCP tool candidates"):
        ToolSelectionService().select(())


def test_discovery_publishes_non_sensitive_summary_event() -> None:
    events = EventBus()
    received = []
    events.subscribe("ToolDiscoveryCompleted", received.append)
    discovery, capabilities, tools = make_discovery(events)
    add_capability(capabilities, "mcp:filesystem")
    tools.register("mcp:filesystem", tool("read_file"))
    discovery.discover(request())
    assert asyncio.run(events.dispatch_once()) is True
    assert received[0].payload["candidate_count"] == 1
