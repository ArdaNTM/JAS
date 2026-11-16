"""Bounded ambient *signal-level* observation from consented PCM16 audio.

This is not sound-event classification or a microphone capture provider.
The upstream authenticated local speech session must explicitly consent and
supply decoded 16 kHz mono little-endian PCM data. No samples are persisted,
networked or passed to MCP; only coarse sanitized metrics reach EventBus.
"""
from __future__ import annotations

import math
import struct
import threading
from dataclasses import dataclass

from aura_core.kernel.events import EventBus, KernelEvent

_SAMPLE_RATE = 16_000
_MIN_SAMPLES = 160
_MAX_SAMPLES = 32_000
_CLIP_AMPLITUDE = 32_700


@dataclass(frozen=True, slots=True)
class AmbientSignalMetrics:
    sample_count: int
    duration_ms: int
    rms: float
    peak: float
    clipped_fraction: float
    level: str
    classification: str = "SIGNAL_ENERGY_ONLY_NOT_SOUND_IDENTITY"


def analyze_pcm16_signal(audio: bytes, *, sample_rate: int = _SAMPLE_RATE) -> AmbientSignalMetrics:
    """Compute bounded numeric energy, not speech content or inferred events."""
    if type(sample_rate) is not int or sample_rate != _SAMPLE_RATE:
        raise ValueError("Only explicit 16kHz mono PCM16 is accepted")
    if not isinstance(audio, bytes) or len(audio) % 2 != 0:
        raise ValueError("Invalid PCM16 byte buffer")
    count = len(audio) // 2
    if not _MIN_SAMPLES <= count <= _MAX_SAMPLES:
        raise ValueError("Audio chunk must contain 10..2000ms of PCM16 samples")
    power = 0
    peak = 0
    clipped = 0
    for (sample,) in struct.iter_unpack("<h", audio):
        value = abs(sample)
        power += sample * sample
        peak = max(peak, value)
        if value >= _CLIP_AMPLITUDE:
            clipped += 1
    rms = math.sqrt(power / count) / 32768.0
    clipped_ratio = clipped / count
    level = "clipping" if clipped_ratio >= 0.01 else ("activity" if rms >= 0.035 else "quiet")
    return AmbientSignalMetrics(
        sample_count=count,
        duration_ms=count * 1000 // _SAMPLE_RATE,
        rms=round(rms, 4),
        peak=round(peak / 32768.0, 4),
        clipped_fraction=round(clipped_ratio, 4),
        level=level,
    )


def _session_id(value: str) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= 128
            or value != value.strip()
            or any(ord(ch) < 32 or ord(ch) == 127 or 0xD800 <= ord(ch) <= 0xDFFF for ch in value)):
        raise ValueError("Invalid speech session ID")
    return value


class ConsentedAmbientSignalObserver:
    """Optional signal-only EventBus projection, never an execution authority.

    Consent is an assertion from the trusted application composition, not a
    user-supplied public HTTP header or an Owner identity verification.
    """

    def __init__(self, events: EventBus) -> None:
        if not isinstance(events, EventBus):
            raise TypeError("Existing Core EventBus is required")
        self._events = events
        self._lock = threading.RLock()
        self._session: str | None = None
        self._generation = 0
        self._last_level: str | None = None

    def start(self, *, session_id: str, microphone_confirmed: bool) -> None:
        session = _session_id(session_id)
        if microphone_confirmed is not True:
            raise PermissionError("Microphone session was not explicitly confirmed")
        with self._lock:
            if self._session is not None and self._session != session:
                raise PermissionError("Another session owns the signal observer")
            self._session = session
            self._generation += 1
            self._last_level = None

    def stop(self, *, session_id: str) -> None:
        session = _session_id(session_id)
        with self._lock:
            if self._session != session:
                raise PermissionError("Cannot stop another audio session")
            self._generation += 1
            self._session = None
            self._last_level = None

    def observe(self, audio: bytes, *, session_id: str) -> AmbientSignalMetrics:
        session = _session_id(session_id)
        with self._lock:
            if self._session != session:
                raise PermissionError("Unconfirmed or wrong audio session")
            generation = self._generation
        result = analyze_pcm16_signal(audio)
        with self._lock:
            # Stop/replace while parsing cancels the event and data return.
            if self._session != session or self._generation != generation:
                raise PermissionError("Audio consent expired during observation")
            if self._last_level != result.level:
                self._last_level = result.level
                self._events.publish(KernelEvent(
                    event_type="AmbientSignalLevelChanged",
                    source_component="aura.ambient_signal",
                    session_id=session,
                    correlation_id=session,
                    payload={
                        "session_id": session,
                        "level": result.level,
                        "rms": result.rms,
                        "peak": result.peak,
                        "duration_ms": result.duration_ms,
                        "classification": result.classification,
                    },
                ))
            return result
