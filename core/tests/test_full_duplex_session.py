from __future__ import annotations

import asyncio
from datetime import datetime, time, timezone

import pytest

from aura_core.application.full_duplex_session import (
    ControlledVisionService, FasterWhisperRecognizer, FullDuplexSessionManager,
    ProactiveNotifier,
)


class Recognizer:
    async def transcribe(self, audio, *, session_id):
        return "stop please"


class Synthesizer:
    async def synthesize(self, text, *, session_id):
        await asyncio.sleep(0)
        return text.encode()


class Player:
    def __init__(self):
        self.started = asyncio.Event()
        self.stopped = 0
        self.cancelled = False

    async def play(self, audio, *, session_id):
        self.started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    async def stop(self, *, session_id):
        self.stopped += 1


def test_full_duplex_session_interrupts_active_playback_on_incoming_audio():
    async def scenario():
        player = Player()
        session = FullDuplexSessionManager(
            recognizer=Recognizer(), synthesizer=Synthesizer(), player=player,
        )
        await session.start("session-1")
        speech = asyncio.create_task(session.speak("Hello there"))
        await asyncio.wait_for(player.started.wait(), timeout=1)
        transcript = await session.ingest_audio(b"audio bytes")
        with pytest.raises(asyncio.CancelledError):
            await speech
        assert transcript == "stop please"
        assert player.cancelled is True
        assert player.stopped >= 1
        assert session.snapshot().state == "listening"
        await session.close()
    asyncio.run(scenario())


def test_vision_requires_explicit_consent_before_capture():
    class Capture:
        def __init__(self):
            self.calls = 0

        async def capture(self):
            self.calls += 1
            return b"image"

    class Vision:
        async def describe(self, image, *, prompt):
            return "A desktop with a terminal."

    async def scenario():
        capture = Capture()
        vision = ControlledVisionService(
            capture=capture, provider=Vision(), consent=lambda _: False,
        )
        with pytest.raises(PermissionError):
            await vision.describe_screen(principal_id="alice")
        assert capture.calls == 0
    asyncio.run(scenario())


def test_proactive_notifications_respect_opt_in_quiet_hours_and_daily_budget():
    async def scenario():
        delivered = []
        async def deliver(**kwargs):
            delivered.append(kwargs)
        notifier = ProactiveNotifier(
            deliver=deliver, budget_per_day=1,
            quiet_start=time(22, 0), quiet_end=time(8, 0),
        )
        night = datetime(2026, 10, 21, 23, 0, tzinfo=timezone.utc)
        morning = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
        assert not await notifier.notify(
            principal_id="alice", message="quiet", opted_in=True, now=night,
        )
        assert not await notifier.notify(
            principal_id="alice", message="not opted in", opted_in=False, now=morning,
        )
        assert await notifier.notify(
            principal_id="alice", message="one update", opted_in=True, now=morning,
        )
        assert not await notifier.notify(
            principal_id="alice", message="second update", opted_in=True, now=morning,
        )
        assert len(delivered) == 1
    asyncio.run(scenario())


def test_faster_whisper_recognizer_decodes_audio_and_passes_samples_to_model(monkeypatch):
    import sys
    import types
    import numpy as np

    observed = {}

    class AudioFrame:
        def __init__(self, values):
            self.values = np.asarray(values, dtype=np.float32).reshape(1, -1)

        def to_ndarray(self):
            return self.values

    class Resampler:
        def __init__(self, *, format, layout, rate):
            observed["resampler"] = (format, layout, rate)

        def resample(self, frame):
            if frame is None:
                return []
            return [AudioFrame([0.1, -0.2, 0.3])]

    class Stream:
        type = "audio"
        index = 0

    class Container:
        streams = [Stream()]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def decode(self, *, audio):
            observed["audio_stream_index"] = audio
            return [object()]

    def open_audio(source, *, mode):
        observed["source_type"] = type(source)
        observed["mode"] = mode
        return Container()

    fake_av = types.SimpleNamespace(
        open=open_audio,
        AudioResampler=Resampler,
    )

    class Segment:
        text = " decoded speech "

    class Model:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, samples, **kwargs):
            observed["samples"] = samples
            observed["transcribe_kwargs"] = kwargs
            return iter([Segment()]), object()

    fake_whisper = types.SimpleNamespace(WhisperModel=Model)
    monkeypatch.setitem(sys.modules, "av", fake_av)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_whisper)

    async def scenario():
        recognizer = FasterWhisperRecognizer()
        assert await recognizer.transcribe(b"encoded audio", session_id="session-1") == "decoded speech"

    asyncio.run(scenario())

    assert observed["source_type"] is __import__("io").BytesIO
    assert observed["mode"] == "r"
    assert observed["resampler"] == ("fltp", "mono", 16000)
    assert observed["audio_stream_index"] == 0
    assert isinstance(observed["samples"], np.ndarray)
    assert observed["samples"].dtype == np.float32
    assert observed["samples"].tolist() == pytest.approx([0.1, -0.2, 0.3])
    assert observed["transcribe_kwargs"] == {"beam_size": 1, "vad_filter": True}
