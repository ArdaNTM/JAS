"""Strict local Kokoro voice profile validation at the existing MCP tool boundary.

The model's real audio synthesis remains with the registered Kokoro MCP provider.
This module only validates and normalizes request inputs. It does not grant
execution authority, access files or invoke models itself.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from aura_core.tts.text import clean_for_speech

SUPPORTED_ENGLISH_VOICES: tuple[str, ...] = (
    "af_bella", "af_heart", "af_nicole", "af_sarah",
    "am_adam", "am_michael",
)
MIN_SPEED = 0.75
MAX_SPEED = 1.35
MAX_TEXT_CHARACTERS = 4_000


@dataclass(frozen=True, slots=True)
class KokoroVoiceRequest:
    text: str
    voice: str
    speed: float


def validate_kokoro_voice_request(
    text: object,
    voice: object = "af_heart",
    speed: object = 1.0,
) -> KokoroVoiceRequest:
    """Reject malformed text, unknown voice and unsafe/out-of-bounds rate.

    The current Kokoro MCP service sets `lang_code="a"`, so this phase limits
    voice selection to the explicitly approved English voices. This does NOT
    change the separate Turkish Piper provider or promise automatic downloads.
    """
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARACTERS:
        raise ValueError("Kokoro text must contain 1..4000 characters")
    cleaned = clean_for_speech(text)
    if not cleaned:
        raise ValueError("Kokoro speech contains no speakable content")
    if not isinstance(voice, str) or voice not in SUPPORTED_ENGLISH_VOICES:
        raise ValueError("Unsupported Kokoro English voice")
    if type(speed) not in (int, float):
        raise ValueError("Kokoro speech speed must be a finite number")
    requested_speed = float(speed)
    if not math.isfinite(requested_speed) or not MIN_SPEED <= requested_speed <= MAX_SPEED:
        raise ValueError("Kokoro speech speed outside allowed range")
    return KokoroVoiceRequest(text=cleaned, voice=voice, speed=requested_speed)
