from __future__ import annotations

from mcp.client.stdio import StdioServerParameters

from aura_core.kernel.capabilities import (
    CapabilityDefinition,
    CapabilityCategory,
    ProviderType,
)
from aura_core.kernel.services import (
    ServiceCategory,
    ServiceDefinition,
)
from aura_core.mcp.connection import MCPConnection
from aura_core.mcp.mcp_provider import MCPProvider
from aura_core.mcp.provider import (
    ProviderDefinition,
    ProviderRegistry,
)
from aura_core.mcp.tool_registry import MCPToolRegistry

from .config import ResearchMCPConfig


async def register_research_mcp(
    *,
    config: ResearchMCPConfig,
    services,
    providers: ProviderRegistry,
    capabilities,
    tools: MCPToolRegistry,
):
    service = services.register(
        ServiceDefinition(
            name=config.service_name,
            version=config.service_version,
            provider="mcp",
            category=ServiceCategory.MCP,
        ),
        object(),
    )

    connection = MCPConnection()

    if config.transport == "http":
        assert config.endpoint is not None

        await connection.connect_http(
            config.endpoint
        )

    else:
        assert config.command is not None

        await connection.connect_stdio(
            StdioServerParameters(
                command=config.command,
                args=list(config.args),
            )
        )

    provider = MCPProvider(
        connection
    )

    providers.register(
        ProviderDefinition(
            provider_id=config.provider_id,
            name=config.service_name,
            version=config.service_version,
            service_id=service.service_id,
        ),
        provider,
    )

    discovered_tools = await provider.list_tools()

    available_names = {
        tool.name
        for tool in discovered_tools
    }

    required_tools = {
        config.search_tool_name,
        config.fetch_tool_name,
    }

    missing = sorted(
        required_tools
        - available_names
    )

    if missing:
        await provider.close()

        raise RuntimeError(
            "Research MCP server does not expose "
            "required configured tools: "
            + ", ".join(missing)
        )

    tools.register_many(
        config.provider_id,
        discovered_tools,
    )

    capabilities.register(
        CapabilityDefinition(
            capability_id=(
                config.capability_id
            ),
            name="Internet Research",
            version="1.0.0",
            description=(
                "Internet research through "
                "a registered MCP provider."
            ),
            provider_id=config.provider_id,
            provider_type=ProviderType.MCP,
            category=CapabilityCategory.RESEARCH,
        )
    )

    if (
        config.fetch_capability_id
        != config.capability_id
    ):
        capabilities.register(
            CapabilityDefinition(
                capability_id=(
                    config.fetch_capability_id
                ),
                name="Internet Fetch",
                version="1.0.0",
                description=(
                    "Fetch public research resources "
                    "through a registered MCP provider."
                ),
                provider_id=config.provider_id,
                provider_type=ProviderType.MCP,
                category=CapabilityCategory.RESEARCH,
            )
        )

    return provider
