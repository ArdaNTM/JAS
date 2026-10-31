"""Local-only Kokoro-82M MCP service. Model import is lazy to keep Core boot deterministic."""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
from pathlib import Path
from threading import Lock
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server, ServerRequestContext


# ONNX session is reused across chunks. The process stays inside the
# existing governed MCP service and cannot bypass PermissionEngine.
_onnx = None
_onnx_lock = Lock()


def synthesize(text: str, voice: str, speed: float) -> dict[str, Any]:
    if not text.strip():
        raise ValueError("text is required")
    import soundfile as sf
    buffer = io.BytesIO()
    if os.getenv("AURA_KOKORO_ONNX_ENABLED", "0") == "1":
        global _onnx
        model = Path(os.getenv("AURA_KOKORO_ONNX_MODEL", ""))
        voices = Path(os.getenv("AURA_KOKORO_ONNX_VOICES", ""))
        if not model.is_file() or not voices.is_file():
            raise RuntimeError("Owner-provisioned Kokoro ONNX model/voices are missing")
        try:
            from kokoro_onnx import Kokoro
        except ImportError as exc:
            raise RuntimeError("kokoro-onnx is required for native ONNX TTS") from exc
        with _onnx_lock:
            if _onnx is None:
                _onnx = Kokoro(str(model), str(voices))
            samples, sample_rate = _onnx.create(text, voice=voice, speed=speed, lang="en-us")
        sf.write(buffer, samples, sample_rate, format="WAV")
    else:
        # Legacy TTS remains available only when the Nirvana flag is disabled.
        if os.getenv("AURA_NIRVANA_VOICE_ENABLED", "0") == "1":
            raise RuntimeError("Nirvana requires AURA_KOKORO_ONNX_ENABLED=1")
        from kokoro import KPipeline
        pipeline = KPipeline(lang_code="a")
        chunks = list(pipeline(text, voice=voice, speed=speed))
        if not chunks:
            raise RuntimeError("Kokoro produced no audio")
        sf.write(buffer, chunks[0].audio, 24000, format="WAV")
    return {"mime_type": "audio/wav", "audio_base64": base64.b64encode(buffer.getvalue()).decode("ascii"), "voice": voice}


async def handle_list_tools(ctx: ServerRequestContext, params: Any) -> types.ListToolsResult:
    return types.ListToolsResult(tools=[types.Tool(name="synthesize", description="Create local WAV speech with Kokoro-82M.", inputSchema={"type":"object","properties":{"text":{"type":"string"},"voice":{"type":"string","default":"af_heart"},"speed":{"type":"number","default":1.0}},"required":["text"]})])


async def handle_call_tool(ctx: ServerRequestContext, params: types.CallToolRequestParams) -> types.CallToolResult:
    if params.name != "synthesize":
        return types.CallToolResult(content=[types.TextContent(type="text", text="Unknown tool")], isError=True)
    try:
        args = params.arguments or {}
        result = await asyncio.to_thread(synthesize, str(args.get("text", "")), str(args.get("voice", "af_heart")), float(args.get("speed", 1.0)))
        return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps({"mime_type": result["mime_type"], "voice": result["voice"]}))], structuredContent=result)
    except Exception as exc:
        return types.CallToolResult(content=[types.TextContent(type="text", text=f"{type(exc).__name__}: {exc}")], isError=True)


server = Server("aura-kokoro-tts", on_list_tools=handle_list_tools, on_call_tool=handle_call_tool)

async def main() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
