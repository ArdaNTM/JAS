from __future__ import annotations

import asyncio
import io
import math
import struct
import wave

import pytest

from aura_core.application.full_duplex_session import FullDuplexSessionManager
from aura_core.application.voice_prosody import (
    ProsodyCueAnalyzer,
    VoiceProsodyService,
    register_voice_prosody_service,
)
from aura_core.kernel.events import EventBus
from aura_core.kernel.services import ServiceRegistry


def make_wav(*, frequency=180.0, amplitude=0.25, duration=1.2, sample_rate=16000, channels=1):
    buffer = io.BytesIO()
    count = int(sample_rate * duration)
    with wave.open(buffer, "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        frames = bytearray()
        for index in range(count):
            envelope = 0.0 if duration * 0.35 <= index / sample_rate <= duration * 0.55 else 1.0
            sample = int(32767 * amplitude * envelope * math.sin(2 * math.pi * frequency * index / sample_rate))
            for _ in range(channels):
                frames.extend(struct.pack("<h", sample))
        output.writeframes(bytes(frames))
    return buffer.getvalue()


def test_analyzer_extracts_bounded_pitch_energy_and_pauses():
    cues = ProsodyCueAnalyzer().analyze(make_wav())
    assert cues.duration_seconds == pytest.approx(1.2, abs=0.01)
    assert cues.median_pitch_hz == pytest.approx(180.0, abs=8.0)
    assert 0.10 <= cues.pause_ratio <= 0.35
    assert cues.peak_dbfs < 0
    assert cues.delivery_style in {"quiet", "high_energy", "expressive", "steady", "undetermined"}
    assert 0 <= cues.confidence <= 1


def test_stereo_pcm_is_downmixed_and_analyzed():
    cues = ProsodyCueAnalyzer().analyze(make_wav(channels=2))
    assert cues.median_pitch_hz == pytest.approx(180.0, abs=8.0)


@pytest.mark.parametrize("payload", [b"", b"not-a-wave"])
def test_invalid_audio_fails_closed(payload):
    with pytest.raises(ValueError):
        ProsodyCueAnalyzer().analyze(payload)


def test_service_publishes_only_metadata_and_never_raw_audio():
    bus = EventBus()
    received = []
    bus.subscribe("SpeechProsodyCues", received.append)
    service = VoiceProsodyService(event_bus=bus)
    cues = service.analyze_consented_audio(make_wav(), session_id="session-1")
    import asyncio
    assert asyncio.run(bus.dispatch_once()) is True
    event = received[0]
    assert event.correlation_id == "session-1"
    assert event.payload["interpretation"] == "acoustic_delivery_only"
    assert event.payload["identity_or_emotion_inference"] is False
    assert event.payload["raw_audio_retained"] is False
    assert "audio" not in event.payload
    assert event.payload["median_pitch_hz"] == cues.median_pitch_hz


def test_service_registers_in_authoritative_service_registry():
    bus = EventBus()
    registry = ServiceRegistry(bus)
    service_id = register_voice_prosody_service(registry, bus)
    service = registry.resolve(service_id)
    assert isinstance(service, VoiceProsodyService)
    assert registry.get(service_id).definition.capabilities == frozenset({"speech.prosody.analyze"})


def test_rejects_invalid_session_scope():
    service = VoiceProsodyService(event_bus=EventBus())
    with pytest.raises(ValueError):
        service.analyze_consented_audio(make_wav(), session_id="")


def test_full_duplex_session_runs_prosody_on_already_ingested_audio():
    class Recognizer:
        async def transcribe(self, audio, *, session_id):
            return "hello"

    class Synthesizer:
        async def synthesize(self, text, *, session_id):
            return b""

    class Player:
        async def play(self, audio, *, session_id):
            return None

        async def stop(self, *, session_id):
            return None

    async def scenario():
        bus = EventBus()
        observed = []
        bus.subscribe("*", observed.append)
        service = VoiceProsodyService(event_bus=bus)
        manager = FullDuplexSessionManager(
            recognizer=Recognizer(),
            synthesizer=Synthesizer(),
            player=Player(),
            event_bus=bus,
            prosody_analyzer=service,
        )
        await manager.start("session-integrated")
        assert await manager.ingest_audio(make_wav()) == "hello"
        while bus.snapshot()["queued_total"]:
            await bus.dispatch_once()
        event_types = [event.event_type for event in observed]
        assert "SpeechProsodyCues" in event_types
        assert "SpeechProsodyAnalysisCompleted" in event_types
        assert "SpeechTranscript" in event_types

    asyncio.run(scenario())
