"""Bounded local prosody cues for already-consented speech audio.

This module measures acoustic delivery only. It does not identify a speaker,
infer a mental/medical state, authenticate a person, or retain raw audio.
"""
from __future__ import annotations

import io
import math
import statistics
import wave
from dataclasses import asdict, dataclass
from typing import Any

_MAX_AUDIO_BYTES = 8_000_000
_MAX_DURATION_SECONDS = 30.0
_MIN_SAMPLE_RATE = 8_000
_MAX_SAMPLE_RATE = 48_000
_FRAME_SECONDS = 0.025
_HOP_SECONDS = 0.010


@dataclass(frozen=True, slots=True)
class ProsodyCues:
    duration_seconds: float
    rms_dbfs: float
    peak_dbfs: float
    pause_ratio: float
    voiced_ratio: float
    median_pitch_hz: float | None
    pitch_range_hz: float | None
    delivery_style: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProsodyCueAnalyzer:
    """Analyze bounded PCM WAV audio without external models or network access."""

    def analyze(self, audio: bytes) -> ProsodyCues:
        if not isinstance(audio, bytes) or not audio or len(audio) > _MAX_AUDIO_BYTES:
            raise ValueError("Audio must be non-empty bytes within the 8 MB limit")
        samples, sample_rate = self._decode_wav(audio)
        duration = len(samples) / sample_rate
        if not 0.10 <= duration <= _MAX_DURATION_SECONDS:
            raise ValueError("Audio duration must be between 0.1 and 30 seconds")

        # Downsample deterministically to at most 8 kHz for bounded pitch analysis.
        stride = max(1, math.ceil(sample_rate / 8_000))
        analysis_rate = sample_rate / stride
        samples = samples[::stride]
        frame_size = max(1, round(analysis_rate * _FRAME_SECONDS))
        hop_size = max(1, round(analysis_rate * _HOP_SECONDS))
        frame_rms: list[float] = []
        pitch_values: list[float] = []
        peak = 0.0

        for start in range(0, max(1, len(samples) - frame_size + 1), hop_size):
            frame = samples[start:start + frame_size]
            if len(frame) < frame_size:
                break
            energy = sum(value * value for value in frame) / frame_size
            rms = math.sqrt(energy)
            frame_rms.append(rms)
            peak = max(peak, max(abs(value) for value in frame))
            if rms >= 0.008:
                pitch = self._estimate_pitch(frame, analysis_rate)
                if pitch is not None:
                    pitch_values.append(pitch)

        if not frame_rms:
            raise ValueError("Audio contains no analyzable frames")
        whole_rms = math.sqrt(sum(value * value for value in samples) / len(samples))
        pause_ratio = sum(value < 0.008 for value in frame_rms) / len(frame_rms)
        voiced_ratio = len(pitch_values) / len(frame_rms)
        median_pitch = statistics.median(pitch_values) if pitch_values else None
        pitch_range = (
            max(pitch_values) - min(pitch_values) if len(pitch_values) >= 2 else None
        )
        variation = statistics.pstdev(frame_rms) if len(frame_rms) >= 2 else 0.0
        rms_dbfs = self._dbfs(whole_rms)
        peak_dbfs = self._dbfs(peak)

        if voiced_ratio < 0.08:
            style = "undetermined"
        elif rms_dbfs < -32.0:
            style = "quiet"
        elif rms_dbfs > -13.0:
            style = "high_energy"
        elif variation > 0.055 or (pitch_range is not None and pitch_range > 95.0):
            style = "expressive"
        else:
            style = "steady"

        confidence = min(1.0, max(0.0, voiced_ratio * min(1.0, duration / 1.0)))
        return ProsodyCues(
            duration_seconds=round(duration, 3),
            rms_dbfs=round(rms_dbfs, 2),
            peak_dbfs=round(peak_dbfs, 2),
            pause_ratio=round(pause_ratio, 3),
            voiced_ratio=round(voiced_ratio, 3),
            median_pitch_hz=round(median_pitch, 1) if median_pitch is not None else None,
            pitch_range_hz=round(pitch_range, 1) if pitch_range is not None else None,
            delivery_style=style,
            confidence=round(confidence, 3),
        )

    @staticmethod
    def _dbfs(value: float) -> float:
        return 20.0 * math.log10(max(value, 1e-8))

    @staticmethod
    def _decode_wav(audio: bytes) -> tuple[list[float], int]:
        try:
            with wave.open(io.BytesIO(audio), "rb") as source:
                if source.getcomptype() != "NONE":
                    raise ValueError("Only uncompressed PCM WAV is supported")
                channels = source.getnchannels()
                width = source.getsampwidth()
                sample_rate = source.getframerate()
                frame_count = source.getnframes()
                if channels not in (1, 2):
                    raise ValueError("WAV must contain one or two channels")
                if width not in (1, 2, 3, 4):
                    raise ValueError("Unsupported PCM sample width")
                if not _MIN_SAMPLE_RATE <= sample_rate <= _MAX_SAMPLE_RATE:
                    raise ValueError("WAV sample rate is outside the 8-48 kHz bound")
                if frame_count <= 0 or frame_count / sample_rate > _MAX_DURATION_SECONDS:
                    raise ValueError("WAV frame count is outside the duration bound")
                raw = source.readframes(frame_count)
        except (wave.Error, EOFError) as exc:
            raise ValueError("Invalid PCM WAV audio") from exc

        bytes_per_frame = channels * width
        if len(raw) != frame_count * bytes_per_frame:
            raise ValueError("Truncated PCM WAV payload")
        values: list[float] = []
        for offset in range(0, len(raw), bytes_per_frame):
            channel_values = []
            for channel in range(channels):
                index = offset + channel * width
                chunk = raw[index:index + width]
                if width == 1:
                    sample = (chunk[0] - 128) / 128.0
                elif width == 2:
                    sample = int.from_bytes(chunk, "little", signed=True) / 32768.0
                elif width == 3:
                    sample = int.from_bytes(chunk, "little", signed=True) / 8_388_608.0
                else:
                    sample = int.from_bytes(chunk, "little", signed=True) / 2_147_483_648.0
                channel_values.append(sample)
            values.append(sum(channel_values) / channels)
        return values, sample_rate

    @staticmethod
    def _estimate_pitch(frame: list[float], sample_rate: float) -> float | None:
        # Remove DC offset before autocorrelation.
        mean = sum(frame) / len(frame)
        centered = [value - mean for value in frame]
        energy = sum(value * value for value in centered)
        if energy <= 1e-8:
            return None
        min_lag = max(2, int(sample_rate / 400.0))
        max_lag = min(len(centered) // 2, int(sample_rate / 70.0))
        best_lag = 0
        best_score = 0.0
        for lag in range(min_lag, max_lag + 1):
            score = sum(
                centered[index] * centered[index + lag]
                for index in range(len(centered) - lag)
            ) / energy
            if score > best_score:
                best_score = score
                best_lag = lag
        if best_lag == 0 or best_score < 0.30:
            return None
        pitch = sample_rate / best_lag
        return pitch if 65.0 <= pitch <= 450.0 else None


class VoiceProsodyService:
    """ServiceRegistry-compatible adapter emitting metadata-only Kernel events."""

    def __init__(self, *, event_bus, analyzer: ProsodyCueAnalyzer | None = None) -> None:
        self._events = event_bus
        self._analyzer = analyzer or ProsodyCueAnalyzer()

    def analyze_consented_audio(self, audio: bytes, *, session_id: str) -> ProsodyCues:
        if not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 128:
            raise ValueError("A valid active speech session id is required")
        cues = self._analyzer.analyze(audio)
        from aura_core.kernel.events import KernelEvent

        self._events.publish(KernelEvent(
            event_type="SpeechProsodyCues",
            source_component="aura.voice_prosody",
            correlation_id=session_id,
            payload={"session_id": session_id, **cues.to_dict(),
                     "interpretation": "acoustic_delivery_only",
                     "identity_or_emotion_inference": False,
                     "raw_audio_retained": False},
        ))
        return cues


def register_voice_prosody_service(service_registry, event_bus) -> str:
    """Register the local prosody service in the authoritative Kernel registry."""
    from aura_core.kernel.services import ServiceCategory, ServiceDefinition

    service = VoiceProsodyService(event_bus=event_bus)
    definition = ServiceDefinition(
        name="voice-prosody-cues",
        version="1.0.0",
        provider="aura.local",
        category=ServiceCategory.SERVICE,
        capabilities=frozenset({"speech.prosody.analyze"}),
        tags=frozenset({"local", "offline", "audio", "metadata-only"}),
    )
    service_registry.register(definition, service)
    return definition.service_id
