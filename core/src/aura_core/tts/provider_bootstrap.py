from __future__ import annotations

import os
from mcp.client.stdio import StdioServerParameters
from aura_core.kernel.capabilities import CapabilityCategory, CapabilityDefinition, LatencyClass, ProviderType, QualityClass
from aura_core.kernel.services import ServiceCategory, ServiceDefinition
from aura_core.mcp.connection import MCPConnection
from aura_core.mcp.mcp_provider import MCPProvider
from aura_core.mcp.provider import ProviderDefinition
from aura_core.mcp.tool_registry import MCPToolRegistry
from aura_core.tts.config import KokoroMCPConfig


async def register_kokoro_mcp(*, config: KokoroMCPConfig, services, providers, capabilities, tools: MCPToolRegistry):
    service = services.register(ServiceDefinition(name=config.service_name, version=config.service_version, provider="mcp", category=ServiceCategory.MCP), object())
    connection = MCPConnection()
    await connection.connect_stdio(StdioServerParameters(
        command=config.command,
        args=list(config.args),
        env={
            **os.environ,
            "TEMP": r"D:\AURA\JAS\.tmp",
            "TMP": r"D:\AURA\JAS\.tmp",
            "HF_HOME": r"D:\AURA\JAS\.cache\huggingface",
            "XDG_CACHE_HOME": r"D:\AURA\JAS\.cache\xdg",
        },
    ))
    provider = MCPProvider(connection)
    providers.register(ProviderDefinition(provider_id=config.provider_id, name=config.service_name, version=config.service_version, service_id=service.service_id), provider)
    discovered = await provider.list_tools()
    if config.tool_name not in {tool.name for tool in discovered}:
        await provider.close()
        raise RuntimeError("Kokoro MCP server does not expose synthesize")
    tools.register_many(config.provider_id, discovered)
    capabilities.register(CapabilityDefinition(capability_id=config.capability_id, name="Local speech synthesis", version="1.0.0", description="Synthesizes speech through the local Kokoro MCP service.", provider_id=config.provider_id, provider_type=ProviderType.MCP, category=CapabilityCategory.VOICE, priority=100, latency_class=LatencyClass.LOW, quality_class=QualityClass.HIGH, tool_name=config.tool_name, risk_level="low"))
    return provider
