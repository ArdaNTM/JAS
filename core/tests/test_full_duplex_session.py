from __future__ import annotations

import asyncio
from datetime import datetime, time, timezone

import pytest

from aura_core.application.full_duplex_session import (
    ControlledVisionService, FullDuplexSessionManager, ProactiveNotifier,
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
