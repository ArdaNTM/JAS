"""Register the read-only local filesystem MCP provider through Core registries."""
from __future__ import annotations

import os
from mcp.client.stdio import StdioServerParameters

from aura_core.kernel.capabilities import CapabilityCategory, CapabilityDefinition, ProviderType
from aura_core.kernel.services import ServiceCategory, ServiceDefinition
from aura_core.mcp.connection import MCPConnection
from aura_core.mcp.mcp_provider import MCPProvider
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry
from aura_core.mcp.tool_registry import MCPToolRegistry
from aura_core.filesystem.config import LocalFilesystemMCPConfig


async def register_local_filesystem_mcp(
    *, config: LocalFilesystemMCPConfig, services, providers: ProviderRegistry,
    capabilities, tools: MCPToolRegistry,
) -> MCPProvider:
    service = services.register(
        ServiceDefinition(
            name=config.service_name, version=config.service_version,
            provider="mcp", category=ServiceCategory.MCP,
            capabilities={config.capability_id}, tags={"filesystem", "read-only", "test-data"},
        ),
        object(),
    )
    connection = MCPConnection()
    await connection.connect_stdio(
        StdioServerParameters(
            command=config.command,
            args=list(config.args),
            env={
                **os.environ,
            },
        )
    )
    provider = MCPProvider(connection)
    try:
        discovered = await provider.list_tools()
        matching = [tool for tool in discovered if tool.name == config.tool_name]
        if len(matching) != 1:
            raise RuntimeError("Local filesystem MCP must expose exactly one read_file tool")
        schema = matching[0].input_schema
        if not isinstance(schema, dict):
            raise RuntimeError(
                f"Local filesystem MCP returned a non-object input schema: {schema!r}"
            )

        properties = schema.get("properties", {})
        required = schema.get("required", [])
        additional_properties = schema.get("additionalProperties")
        # MCP SDK versions may normalize away additionalProperties. Unknown
        # arguments are also rejected by the server handler itself.
        valid = (
            isinstance(properties, dict)
            and set(properties) == {"path"}
            and isinstance(required, list)
            and "path" in required
            and additional_properties is not True
        )
        if not valid:
            raise RuntimeError(
                "Local filesystem MCP read_file schema is not restricted to path; "
                f"properties={properties!r}, required={required!r}, "
                f"additionalProperties={additional_properties!r}, schema={schema!r}"
            )
        providers.register(
            ProviderDefinition(
                provider_id=config.provider_id, name=config.service_name,
                version=config.service_version, service_id=service.service_id,
            ),
            provider,
        )
        tools.register_many(config.provider_id, matching)
        capabilities.register(
            CapabilityDefinition(
                capability_id=config.capability_id,
                name="Read test-data file",
                version="1.0.0",
                description="Read-only UTF-8 file access restricted to the repository test-data directory.",
                provider_id=config.provider_id,
                provider_type=ProviderType.MCP,
                category=CapabilityCategory.RESEARCH,
                required_permissions=frozenset({config.capability_id}),
                tool_name=config.tool_name,
                risk_level="low",
            )
        )
        return provider
    except Exception:
        await provider.close()
        raise
