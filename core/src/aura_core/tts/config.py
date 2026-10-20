from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class KokoroMCPConfig:
    provider_id: str = "tts.kokoro"
    service_name: str = "kokoro-local-tts"
    service_version: str = "1.0.0"
    capability_id: str = "speech.synthesize"
    operation_id: str = "speech.synthesize"
    tool_name: str = "synthesize"
    command: str = sys.executable
    args: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "KokoroMCPConfig":
        provider = os.getenv("AURA_TTS_PROVIDER", "kokoro").strip().lower()
        if provider not in {"kokoro", "piper"}:
            raise ValueError("AURA_TTS_PROVIDER must be 'kokoro' or 'piper'")
        script_name = "piper_tts_mcp.py" if provider == "piper" else "kokoro_tts_mcp.py"
        script = Path(__file__).resolve().parents[3] / "scripts" / script_name
        raw_args = os.getenv("AURA_TTS_MCP_ARGS", "").strip()
        default_provider_id = "tts.piper" if provider == "piper" else "tts.kokoro"
        default_service_name = "piper-local-tts" if provider == "piper" else "kokoro-local-tts"
        return cls(
            provider_id=os.getenv("AURA_TTS_PROVIDER_ID", default_provider_id),
            service_name=os.getenv("AURA_TTS_SERVICE_NAME", default_service_name),
            command=os.getenv("AURA_TTS_MCP_COMMAND", sys.executable),
            args=tuple(raw_args.split("|")) if raw_args else (str(script),),
        )
