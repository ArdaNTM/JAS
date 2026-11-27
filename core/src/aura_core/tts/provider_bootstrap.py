from __future__ import annotations

import logging
import os

from mcp.client.stdio import StdioServerParameters
from aura_core.kernel.capabilities import CapabilityCategory, CapabilityDefinition, LatencyClass, ProviderType, QualityClass
from aura_core.kernel.services import ServiceCategory, ServiceDefinition
from aura_core.mcp.connection import MCPConnection
from aura_core.mcp.mcp_provider import MCPProvider
from aura_core.mcp.provider import ProviderDefinition
from aura_core.mcp.tool_registry import MCPToolRegistry
from aura_core.tts.config import KokoroMCPConfig

logger = logging.getLogger(__name__)


async def register_kokoro_mcp(*, config: KokoroMCPConfig, services, providers, capabilities, tools: MCPToolRegistry):
    # The SDK timeout is numeric seconds. Discover the tool before publishing
    # any registry entry, so a failed handshake cannot advertise speech.
    connection = MCPConnection(read_timeout_seconds=15.0)
    service = None
    provider_registered = tools_registered = capability_registered = False
    try:
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
        discovered = await provider.list_tools()
        if config.tool_name not in {tool.name for tool in discovered}:
            raise RuntimeError("Local TTS MCP server does not expose synthesize")
        service = services.register(ServiceDefinition(name=config.service_name, version=config.service_version, provider="mcp", category=ServiceCategory.MCP), object())
        providers.register(ProviderDefinition(provider_id=config.provider_id, name=config.service_name, version=config.service_version, service_id=service.service_id), provider)
        provider_registered = True
        tools.register_many(config.provider_id, discovered)
        tools_registered = True
        capabilities.register(CapabilityDefinition(capability_id=config.capability_id, name="Local speech synthesis", version="1.0.0", description="Synthesizes speech through the configured local TTS MCP service.", provider_id=config.provider_id, provider_type=ProviderType.MCP, category=CapabilityCategory.VOICE, priority=100, latency_class=LatencyClass.LOW, quality_class=QualityClass.HIGH, tool_name=config.tool_name, risk_level="low"))
        capability_registered = True
        return provider
    except BaseException:
        # Roll back only entries owned by this attempt; never remove a
        # preexisting provider. Cancellation must propagate after cleanup.
        try:
            if capability_registered:
                capabilities.unregister(config.capability_id, config.provider_id)
            if tools_registered:
                tools.unregister_provider(config.provider_id)
            if provider_registered:
                providers.unregister(config.provider_id)
            if service is not None:
                services.unregister(service.service_id)
        finally:
            try:
                await connection.close()
            except Exception:
                logger.exception("Local TTS MCP connection cleanup failed")
        raise
