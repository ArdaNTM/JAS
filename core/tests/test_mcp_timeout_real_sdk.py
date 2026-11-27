"""Real pinned MCP SDK stdio and composed lifespan regressions."""
from __future__ import annotations

import ast
import asyncio
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters

from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.services import ServiceRegistry
from aura_core.mcp.connection import MCPConnection
from aura_core.mcp.provider import ProviderRegistry
from aura_core.mcp.tool_registry import MCPToolRegistry
from aura_core.tts.config import KokoroMCPConfig
from aura_core.tts.provider_bootstrap import register_kokoro_mcp


@pytest.fixture
def stdio_server(tmp_path):
    # Actual SDK low-level server, no model downloads, GPU or network.
    path = tmp_path / "voice_mcp_fixture.py"
    path.write_text("""
import asyncio
import sys
import mcp.server.stdio
from mcp import types
from mcp.server.lowlevel import Server

mode = sys.argv[1]
async def list_tools(ctx, params):
    names = ["search", "fetch"] if mode == "research" else ["read_file"] if mode == "filesystem" else ["other"] if mode == "missing" else ["synthesize"]
    return types.ListToolsResult(tools=[
        types.Tool(name=name, description="Fixture tool", inputSchema={
            "type": "object", "properties": {"path": {"type": "string"}} if name == "read_file" else {"text": {"type": "string"}},
            "required": ["path"] if name == "read_file" else ["text"],
            "additionalProperties": False,
        }) for name in names
    ])

async def call_tool(ctx, params):
    if (params.arguments or {}).get("text") == "slow":
        await asyncio.sleep(10)
    return types.CallToolResult(content=[types.TextContent(type="text", text="ok")],
        structuredContent={"mime_type": "audio/wav", "audio_base64": "YQ=="})

async def main():
    if mode == "broken":
        raise RuntimeError("intentional fixture startup failure")
    server = Server("voice-regression", on_list_tools=list_tools, on_call_tool=call_tool)
    async with mcp.server.stdio.stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())

asyncio.run(main())
""", encoding="utf-8")
    return path


@pytest.mark.parametrize("value", [15, 15.0, timedelta(seconds=15), None])
def test_timeout_normalization(value):
    connection = MCPConnection(read_timeout_seconds=value)
    assert connection._read_timeout == (None if value is None else 15.0)
    assert connection._read_timeout is None or type(connection._read_timeout) is float


@pytest.mark.parametrize("value", [0, -1, 301, float("nan"), float("inf"), True, "15", timedelta(0)])
def test_invalid_timeout_rejected(value):
    with pytest.raises(ValueError, match="Invalid MCP read timeout"):
        MCPConnection(read_timeout_seconds=value)


def test_real_client_session_handshake_and_timeout(stdio_server):
    async def scenario():
        connection = MCPConnection(read_timeout_seconds=timedelta(seconds=3))
        try:
            await connection.connect_stdio(StdioServerParameters(
                command=sys.executable, args=[str(stdio_server), "tts"],
            ))
            assert isinstance(connection.session, ClientSession)
            assert [tool.name for tool in (await connection.list_tools()).tools] == ["synthesize"]
            assert (await connection.call_tool("synthesize", {"text": "ok"}))["mime_type"] == "audio/wav"
            before = asyncio.get_running_loop().time()
            # MCP SDK raises a protocol timeout rather than necessarily a Python
            # TimeoutError. Check real delay and diagnostic, never mock the SDK.
            with pytest.raises(Exception, match=r"(?i)timed?\s*out|timeout|deadline"):
                await connection.call_tool("synthesize", {"text": "slow"})
            assert 2.5 <= asyncio.get_running_loop().time() - before < 8
        finally:
            await connection.close()
        assert not connection.is_connected and connection._owner is None

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["tts", "missing", "broken"])
def test_real_tts_bootstrap_and_no_partial_registration(stdio_server, mode):
    async def scenario():
        services = ServiceRegistry()
        providers = ProviderRegistry(services)
        capabilities = CapabilityRegistry(services)
        tools = MCPToolRegistry()
        config = KokoroMCPConfig(command=sys.executable, args=(str(stdio_server), mode))
        async def register():
            return await register_kokoro_mcp(config=config, services=services,
                providers=providers, capabilities=capabilities, tools=tools)
        if mode != "tts":
            with pytest.raises(Exception):
                await register()
            assert not services.records() and not providers.records()
            assert not capabilities.records() and not tools.records()
            assert not any(t.get_name() == "aura-mcp-transport-owner" for t in asyncio.all_tasks())
            return
        provider = await register()
        try:
            assert isinstance(provider.connection.session, ClientSession)
            assert capabilities.resolve(config.capability_id).definition.provider_id == config.provider_id
            assert (await provider.call_tool("synthesize", {"text": "Merhaba"}))["audio_base64"] == "YQ=="
        finally:
            await provider.close()

    asyncio.run(scenario())


def test_composed_core_survives_real_optional_tts_startup_failure(tmp_path, monkeypatch, stdio_server):
    monkeypatch.chdir(tmp_path)
    for name, value in {
        "LOCALAPPDATA": str(tmp_path),
        "AURA_STORAGE_MODE": "local",
        "AURA_DISABLE_EXTERNAL_PROVIDERS": "0",
        "AURA_SELF_DISCOVERY_ENABLED": "0",
        "AURA_EVOLUTION_AUTO_ACTIVATE": "0",
        "AURA_BACKGROUND_THINKING_ENABLED": "0",
        "AURA_EVOLUTION_REVIEW_ENABLED": "0",
        "AURA_EVOLUTION_SELF_PATCH_ENABLED": "0",
        "AURA_STAGE_C_ENABLED": "0",
        "AURA_STAGE_C_BROWSER_ENABLED": "0",
        "AURA_EVENT_RUNTIME_ENABLED": "0",
        "AURA_API_BEARER_TOKEN": "t" * 40,
        "AURA_API_PRINCIPAL_ID": "local_owner",
        "AURA_RESEARCH_MCP_TRANSPORT": "stdio",
        "AURA_RESEARCH_MCP_COMMAND": sys.executable,
        "AURA_RESEARCH_MCP_ARGS": str(stdio_server) + "|research",
        "AURA_FILESYSTEM_MCP_COMMAND": sys.executable,
        "AURA_FILESYSTEM_MCP_ARGS": str(stdio_server) + "|filesystem",
        "AURA_TTS_MCP_COMMAND": sys.executable,
        "AURA_TTS_MCP_ARGS": str(stdio_server) + "|broken",
    }.items():
        monkeypatch.setenv(name, value)
    from aura_core.main import build_app
    app = build_app()
    with TestClient(app, headers={"Authorization": "Bearer " + "t" * 40}) as client:
        assert client.get("/health").status_code == 200
        assert app.state.tts_startup_available is False
        assert app.state.speech_session_manager is not None
        health = client.get("/api/speech/health")
        assert health.status_code == 200
        assert health.json()["tts_available"] is False
        assert client.post("/api/speech/synthesize", json={"text": "Merhaba"}).status_code == 503


def test_all_core_mcp_session_timeouts_use_the_central_adapter():
    # Scan the actual full source tree on CI; avoid a second direct SDK
    # timeout call accidentally reintroducing the timedelta regression.
    root = Path(__file__).resolve().parents[1] / "src/aura_core"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", getattr(node.func, "attr", ""))
            if name == "ClientSession" and any(k.arg == "read_timeout_seconds" for k in node.keywords):
                assert path.relative_to(root).as_posix() == "mcp/connection.py"
            if name == "MCPConnection":
                for keyword in node.keywords:
                    if keyword.arg == "read_timeout_seconds" and isinstance(keyword.value, ast.Call):
                        assert getattr(keyword.value.func, "id", "") != "timedelta"
