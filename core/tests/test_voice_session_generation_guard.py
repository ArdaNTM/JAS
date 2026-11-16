"""Race regressions for interruptible voice session generations (#14).

No microphone, model weights, OS permissions, or MCP tool executions are used.
"""
from __future__ import annotations

import asyncio

import pytest

from aura_core.application.full_duplex_session import FullDuplexSessionManager


class GateRecognizer:
    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = []

    async def transcribe(self, audio, *, session_id):
        self.calls.append((session_id, audio))
        self.entered.set()
        await self.release.wait()
        return "old session transcript"


class Synthesizer:
    async def synthesize(self, text, *, session_id):
        return text.encode("utf-8")


class Player:
    def __init__(self):
        self.started = asyncio.Event()
        self.stop_calls = []

    async def play(self, audio, *, session_id):
        self.started.set()
        await asyncio.Future()  # cancellation stops the player

    async def stop(self, *, session_id):
        self.stop_calls.append(session_id)


def _manager(recognizer, player=None):
    return FullDuplexSessionManager(
        recognizer=recognizer, synthesizer=Synthesizer(),
        player=player or Player(),
    )


def test_delayed_transcript_cannot_reopen_closed_or_restarted_session():
    async def scenario():
        recognizer = GateRecognizer()
        mgr = _manager(recognizer)
        await mgr.start("former-owner")
        pending = asyncio.create_task(mgr.ingest_audio(b"old-voice"))
        await asyncio.wait_for(recognizer.entered.wait(), timeout=1)
        await mgr.close()
        assert mgr.snapshot().state == "idle"
        await mgr.start("new-owner")
        recognizer.release.set()
        with pytest.raises(RuntimeError, match="superseded"):
            await asyncio.wait_for(pending, timeout=1)
        result = mgr.snapshot()
        assert result.session_id == "new-owner"
        assert result.state == "listening"
        assert result.last_transcript == ""
        assert recognizer.calls == [("former-owner", b"old-voice")]
        await mgr.close()
    asyncio.run(scenario())


def test_stale_recognition_cannot_interrupt_newer_speech_playback():
    async def scenario():
        recognizer, player = GateRecognizer(), Player()
        mgr = _manager(recognizer, player)
        await mgr.start("session-a")
        pending = asyncio.create_task(mgr.ingest_audio(b"voice"))
        await asyncio.wait_for(recognizer.entered.wait(), timeout=1)
        speaking = asyncio.create_task(mgr.speak("new announcement"))
        await asyncio.wait_for(player.started.wait(), timeout=1)
        recognizer.release.set()
        with pytest.raises(RuntimeError, match="superseded"):
            await asyncio.wait_for(pending, timeout=1)
        assert mgr.snapshot().state == "speaking"
        assert mgr.snapshot().last_transcript == ""
        await mgr.interrupt(reason="test", keep_listening=True)
        with pytest.raises(asyncio.CancelledError):
            await speaking
        assert mgr.snapshot().state == "listening"
        assert player.stop_calls
        await mgr.close()
    asyncio.run(scenario())


def test_cancelling_recognizer_restores_listening_only_for_same_generation():
    async def scenario():
        recognizer = GateRecognizer()
        mgr = _manager(recognizer)
        await mgr.start("session")
        pending = asyncio.create_task(mgr.ingest_audio(b"voice"))
        await asyncio.wait_for(recognizer.entered.wait(), timeout=1)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert mgr.snapshot().state == "listening"
        assert mgr.snapshot().last_transcript == ""
        await mgr.close()
    asyncio.run(scenario())


def test_multiple_audio_turns_use_newest_transcript_only():
    class TwoRecognizer:
        def __init__(self):
            self.entered = [asyncio.Event(), asyncio.Event()]
            self.release = [asyncio.Event(), asyncio.Event()]
            self.count = 0
        async def transcribe(self, audio, *, session_id):
            idx = self.count
            self.count += 1
            self.entered[idx].set()
            await self.release[idx].wait()
            return "old transcript" if idx == 0 else "new transcript"

    async def scenario():
        recognizer = TwoRecognizer()
        mgr = _manager(recognizer)
        await mgr.start("session")
        older = asyncio.create_task(mgr.ingest_audio(b"old"))
        await asyncio.wait_for(recognizer.entered[0].wait(), timeout=1)
        newer = asyncio.create_task(mgr.ingest_audio(b"new"))
        await asyncio.wait_for(recognizer.entered[1].wait(), timeout=1)
        recognizer.release[1].set()
        assert await asyncio.wait_for(newer, timeout=1) == "new transcript"
        recognizer.release[0].set()
        with pytest.raises(RuntimeError, match="superseded"):
            await asyncio.wait_for(older, timeout=1)
        assert mgr.snapshot().last_transcript == "new transcript"
        assert mgr.snapshot().state == "listening"
        await mgr.close()
    asyncio.run(scenario())


def test_existing_barge_in_behavior_still_cancels_playback():
    class InstantRecognizer:
        async def transcribe(self, audio, *, session_id):
            return "user interrupt"

    async def scenario():
        player = Player()
        mgr = _manager(InstantRecognizer(), player)
        await mgr.start("session")
        speaking = asyncio.create_task(mgr.speak("speaking"))
        await asyncio.wait_for(player.started.wait(), timeout=1)
        assert await mgr.ingest_audio(b"incoming audio") == "user interrupt"
        with pytest.raises(asyncio.CancelledError):
            await speaking
        assert mgr.snapshot().state == "listening"
        assert player.stop_calls == ["session"]
        await mgr.close()
    asyncio.run(scenario())
