"""Fail-closed configuration for a genuinely local STT + Piper voice path."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True, slots=True)
class OfflineVoiceConfig:
    stt_model_path: str
    piper_model_path: str
    piper_config_path: str

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "OfflineVoiceConfig | None":
        env = os.environ if environ is None else environ
        mode = env.get("AURA_VOICE_MODE", "standard").strip().casefold()
        if mode != "offline":
            return None
        if env.get("AURA_TTS_PROVIDER", "kokoro").strip().casefold() != "piper":
            raise ValueError("Offline voice mode requires AURA_TTS_PROVIDER=piper")

        stt_raw = env.get("AURA_STT_MODEL_PATH", "").strip()
        if not stt_raw:
            raise ValueError("Offline voice mode requires AURA_STT_MODEL_PATH")
        stt_dir = Path(stt_raw).expanduser()
        if not stt_dir.is_absolute():
            raise ValueError("AURA_STT_MODEL_PATH must be an absolute local directory")
        stt_dir = stt_dir.resolve(strict=True)
        if not stt_dir.is_dir() or not (stt_dir / "model.bin").is_file() or not (stt_dir / "config.json").is_file():
            raise ValueError("Local faster-whisper model must contain model.bin and config.json")
        if not (stt_dir / "tokenizer.json").is_file() and not any(stt_dir.glob("vocabulary.*")):
            raise ValueError("Local faster-whisper model tokenizer/vocabulary is missing")

        piper_raw = env.get("AURA_PIPER_MODEL_PATH", "").strip()
        if not piper_raw:
            raise ValueError("Offline voice mode requires AURA_PIPER_MODEL_PATH")
        piper_model = Path(piper_raw).expanduser()
        if not piper_model.is_absolute():
            raise ValueError("AURA_PIPER_MODEL_PATH must be an absolute local file")
        piper_model = piper_model.resolve(strict=True)
        if not piper_model.is_file() or piper_model.suffix.casefold() != ".onnx":
            raise ValueError("AURA_PIPER_MODEL_PATH must reference a local ONNX voice model")

        config_raw = env.get("AURA_PIPER_CONFIG_PATH", "").strip()
        config = Path(config_raw).expanduser() if config_raw else Path(str(piper_model) + ".json")
        if not config.is_absolute():
            raise ValueError("AURA_PIPER_CONFIG_PATH must be an absolute local file")
        config = config.resolve(strict=True)
        if not config.is_file():
            raise ValueError("Local Piper voice configuration is missing")
        try:
            metadata = json.loads(config.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Local Piper voice configuration is invalid") from exc
        language = metadata.get("language", {})
        language_code = language.get("code") if isinstance(language, dict) else language
        if language_code not in {"tr_TR", "tr-TR"}:
            raise ValueError("Offline voice mode currently requires a Turkish tr_TR Piper voice")
        return cls(str(stt_dir), str(piper_model), str(config))
