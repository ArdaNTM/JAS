"""Local Turkish Piper voice behind AURA's existing MCP/Gateway boundary.

No implicit voice download; voice model and its licensing are managed by the
operator. Cache voice loading to remove the per-utterance ONNX startup cost.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import threading
import wave
from pathlib import Path
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server, ServerRequestContext

_voice_lock = threading.Lock()
_cached_voice: Any = None
_cached_identity: tuple[str, str] | None = None


def _voice_paths() -> tuple[Path, Path]:
    raw = os.getenv("AURA_PIPER_MODEL_PATH", "").strip()
    if not raw:
        raise RuntimeError("AURA_PIPER_MODEL_PATH is required for local Turkish Piper speech.")
    model = Path(raw).expanduser()
    config_raw = os.getenv("AURA_PIPER_CONFIG_PATH", "").strip()
    config = Path(config_raw).expanduser() if config_raw else Path(str(model) + ".json")
    if not model.is_file() or model.suffix.lower() != ".onnx":
        raise RuntimeError("Piper ONNX voice model is missing.")
    if not config.is_file():
        raise RuntimeError("Piper voice configuration .onnx.json is missing.")
    # Do not accidentally use an English voice for a Turkish interface.
    metadata = json.loads(config.read_text(encoding="utf-8-sig"))
    language = metadata.get("language", {})
    language_code = language.get("code") if isinstance(language, dict) else language
    if language_code not in ("tr_TR", "tr-TR"):
        raise RuntimeError("AURA Turkish TTS requires a tr_TR Piper voice.")
    return model, config


def synthesize(text: str) -> dict[str, Any]:
    global _cached_voice, _cached_identity
    text = text.strip()
    if not text or len(text) > 4000:
        raise ValueError("Speech text must have 1..4000 characters")
    model, config = _voice_paths()
    identity = (str(model.resolve()), str(config.resolve()))
    try:
        from piper import PiperVoice
    except ImportError as exc:
        raise RuntimeError("Piper selected but piper-tts is not installed in the Core Python environment.") from exc
    with _voice_lock:
        if _cached_voice is None or _cached_identity != identity:
            _cached_voice = PiperVoice.load(str(model), config_path=str(config))
            _cached_identity = identity
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            _cached_voice.synthesize_wav(text, wav_file)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    if len(encoded) > 16_000_000:
        raise RuntimeError("Piper synthesized audio exceeds delivery limit")
    return {
        "mime_type": "audio/wav",
        "audio_base64": encoded,
        "voice": model.stem,
        "provider": "piper",
    }


async def handle_list_tools(ctx: ServerRequestContext, params: Any) -> types.ListToolsResult:
    return types.ListToolsResult(tools=[types.Tool(
        name="synthesize",
        description="Synthesize local Turkish speech with a configured Piper voice.",
        inputSchema={
            "type": "object",
            "properties": {"text": {"type": "string", "maxLength": 4000}},
            "required": ["text"],
            "additionalProperties": False,
        },
    )])


async def handle_call_tool(ctx: ServerRequestContext, params: types.CallToolRequestParams) -> types.CallToolResult:
    if params.name != "synthesize":
        return types.CallToolResult(content=[types.TextContent(type="text", text="Unknown tool")], isError=True)
    try:
        result = await asyncio.to_thread(synthesize, str((params.arguments or {}).get("text", "")))
        # FullDuplexSessionManager's EventBusAudioPlayer consumes the structured
        # result, not a JSON string in the MCP text content.
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps({
                "mime_type": result["mime_type"], "voice": result["voice"],
            }))],
            structuredContent=result,
        )
    except Exception as exc:
        # Return only an error class; never include local paths or provider secrets.
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Piper synthesis failed ({type(exc).__name__})")],
            isError=True,
        )


async def main() -> None:
    server = Server(
        "aura-piper-tts",
        on_list_tools=handle_list_tools,
        on_call_tool=handle_call_tool,
    )
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
