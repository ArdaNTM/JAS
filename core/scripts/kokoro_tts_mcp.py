"""Local-only Kokoro-82M MCP service. Model import is lazy to keep Core boot deterministic."""
from __future__ import annotations

import asyncio
import base64
import io
import json
from typing import Any

from aura_core.tts.kokoro_guard import (
    MAX_SPEED, MAX_TEXT_CHARACTERS, MIN_SPEED,
    SUPPORTED_ENGLISH_VOICES, validate_kokoro_voice_request,
)

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server, ServerRequestContext


def synthesize(text: object, voice: object, speed: object) -> dict[str, Any]:
    request = validate_kokoro_voice_request(text, voice, speed)
    try:
        from kokoro import KPipeline
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError("Local Kokoro runtime is unavailable") from exc

    pipeline = KPipeline(lang_code="a")
    buffer = io.BytesIO()
    total_samples = 0
    # No list() materialization; multiple returned sentences are all spoken.
    # Cap maximum raw audio duration to 90 seconds at 24kHz mono PCM16.
    with sf.SoundFile(buffer, mode="w", samplerate=24000, channels=1,
                      format="WAV", subtype="PCM_16") as wav:
        for chunk in pipeline(request.text, voice=request.voice, speed=request.speed):
            audio = getattr(chunk, "audio", None)
            try:
                count = len(audio) if audio is not None else 0
            except TypeError as exc:
                raise RuntimeError("Kokoro produced invalid audio") from exc
            if count < 0 or count > 24_000 * 90 - total_samples:
                raise RuntimeError("Kokoro output exceeds bounded audio duration")
            if count:
                wav.write(audio)
                total_samples += count
    if total_samples == 0:
        raise RuntimeError("Kokoro produced no audio")
    output = buffer.getvalue()
    encoded = base64.b64encode(output).decode("ascii")
    if len(encoded) > 16_000_000:
        raise RuntimeError("Kokoro output exceeds bounded delivery size")
    return {"mime_type": "audio/wav", "audio_base64": encoded, "voice": request.voice}


async def handle_list_tools(ctx: ServerRequestContext, params: Any) -> types.ListToolsResult:
    return types.ListToolsResult(tools=[types.Tool(
        name="synthesize",
        description="Create bounded local English WAV speech with Kokoro-82M.",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "minLength": 1, "maxLength": MAX_TEXT_CHARACTERS},
                "voice": {"type": "string", "default": "af_heart", "enum": list(SUPPORTED_ENGLISH_VOICES)},
                "speed": {"type": "number", "default": 1.0, "minimum": MIN_SPEED, "maximum": MAX_SPEED},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    )])


async def handle_call_tool(ctx: ServerRequestContext, params: types.CallToolRequestParams) -> types.CallToolResult:
    if params.name != "synthesize":
        return types.CallToolResult(content=[types.TextContent(type="text", text="Unknown tool")], isError=True)
    try:
        args = params.arguments or {}
        if not isinstance(args, dict):
            raise ValueError("Invalid speech arguments")
        result = await asyncio.to_thread(
            synthesize, args.get("text", ""), args.get("voice", "af_heart"),
            args.get("speed", 1.0),
        )
        return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps({"mime_type": result["mime_type"], "voice": result["voice"]}))], structuredContent=result)
    except Exception as exc:
        # Do not return model paths, user text, tool arguments or credentials.
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Kokoro synthesis failed ({type(exc).__name__})")],
            isError=True,
        )


server = Server("aura-kokoro-tts", on_list_tools=handle_list_tools, on_call_tool=handle_call_tool)

async def main() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
