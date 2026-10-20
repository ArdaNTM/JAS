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
        script = Path(__file__).resolve().parents[3] / "scripts" / "kokoro_tts_mcp.py"
        raw_args = os.getenv("AURA_KOKORO_MCP_ARGS", "").strip()
        return cls(provider_id=os.getenv("AURA_KOKORO_MCP_PROVIDER_ID", "tts.kokoro"), command=os.getenv("AURA_KOKORO_MCP_COMMAND", sys.executable), args=tuple(raw_args.split("|")) if raw_args else (str(script),))
