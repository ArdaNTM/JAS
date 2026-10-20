"""Optional local Piper TTS MCP provider.

Configure AURA_TTS_PROVIDER=piper and point AURA_PIPER_MODEL_PATH at a
verified Turkish Piper ONNX voice model. Model files are intentionally not
downloaded or bundled by AURA.
"""
from __future__ import annotations

import asyncio
import base64
import io
import os
import wave
from pathlib import Path
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server, ServerRequestContext


def synthesize(text: str) -> dict[str, Any]:
    if not text.strip():
        raise ValueError("text is required")
    model_path = Path(os.getenv("AURA_PIPER_MODEL_PATH", "")).expanduser()
    config_value = os.getenv("AURA_PIPER_CONFIG_PATH", "").strip()
    if not str(model_path) or not model_path.is_file():
        raise RuntimeError(
            "Piper voice model is not configured. Set AURA_PIPER_MODEL_PATH "
            "to a verified Turkish Piper .onnx voice model."
        )
    config_path = Path(config_value).expanduser() if config_value else Path(str(model_path) + ".json")
    if not config_path.is_file():
        raise RuntimeError(
            "Piper voice configuration is missing. Set AURA_PIPER_CONFIG_PATH "
            "or place the model's .onnx.json file beside the model."
        )
    try:
        from piper import PiperVoice
    except ImportError as exc:
        raise RuntimeError("Piper TTS is selected but piper-tts is not installed.") from exc

    voice = PiperVoice.load(str(model_path), config_path=str(config_path))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)
    return {
        "mime_type": "audio/wav",
        "audio_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
        "voice": model_path.stem,
        "provider": "piper",
    }


async def handle_list_tools(ctx: ServerRequestContext, params: Any) -> types.ListToolsResult:
    return types.ListToolsResult(tools=[types.Tool(
        name="synthesize",
        description="Synthesize local speech with a configured Piper voice model.",
        inputSchema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    )])


async def handle_call_tool(ctx: ServerRequestContext, params: types.CallToolRequestParams) -> types.CallToolResult:
    if params.name != "synthesize":
        return types.CallToolResult(content=[types.TextContent(type="text", text="Unknown tool")], isError=True)
    try:
        result = await asyncio.to_thread(synthesize, str((params.arguments or {}).get("text", "")))
        return types.CallToolResult(content=[types.TextContent(type="text", text=__import__("json").dumps(result))])
    except Exception as exc:
        return types.CallToolResult(content=[types.TextContent(type="text", text=str(exc))], isError=True)


async def main() -> None:
    server = Server("aura-piper-tts")
    server.list_tools()(handle_list_tools)
    server.call_tool()(handle_call_tool)
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
