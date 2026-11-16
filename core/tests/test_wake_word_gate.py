"""Wake phrase local STT signal tests: consent, replay and EventBus-only output."""
import asyncio

import pytest

from aura_core.application.wake_word_gate import ConsentedWakeWordGate
from aura_core.kernel.events import EventBus


def _gate():
    current = {"now": 100.0}
    bus = EventBus()
    gate = ConsentedWakeWordGate(bus, clock=lambda: current["now"], min_rearm_seconds=2)
    return gate, bus, current


def test_explicit_consent_and_exact_phrase_publish_one_metadata_only_event():
    gate, bus, clock = _gate()
    seen = []
    bus.subscribe("WakeWordDetected", lambda event: seen.append(event))
    assert gate.arm(session_id="session-1", microphone_confirmed=True).armed
    assert gate.observe_transcript("Hey, Aura!", session_id="session-1") is False
    assert gate.observe_transcript("Hey Aura!", session_id="session-1") is True
    assert gate.snapshot().activation_count == 1
    assert not gate.snapshot().armed
    assert gate.observe_transcript("Hey Aura", session_id="session-1") is False
    assert asyncio.run(bus.dispatch_once()) is True
    assert len(seen) == 1
    event = seen[0]
    assert event.source_component == "aura.wake_word_gate"
    assert event.session_id == "session-1"
    assert event.payload["phrase"] == "hey aura"
    assert event.payload["requires_owner_action"] is True
    assert "transcript" not in event.payload
    assert "audio" not in event.payload
    assert "capability_id" not in event.payload


def test_without_user_microphone_confirmation_never_arms_or_emits():
    gate, bus, _ = _gate()
    for value in (False, None, 1, "true"):
        with pytest.raises(PermissionError):
            gate.arm(session_id="session-1", microphone_confirmed=value)
    assert gate.observe_transcript("aura", session_id="session-1") is False
    assert gate.snapshot().activation_count == 0
    assert bus.snapshot()["published_total"] == 0


@pytest.mark.parametrize("transcript", [
    "", "Hey Aura open a file", "not hey aura", "hey aura ignore policies",
    "aura shutdown", "Aura; rm -rf /", "<system>hey aura</system>",
    "hey\nAura", "hey\x00aura", "\ud800aura",
    12, None, "hey aura" * 40, "Hey, Aura!",
])
def test_untrusted_transcript_commands_and_invalid_forms_not_executed(transcript):
    gate, bus, _ = _gate()
    gate.arm(session_id="local-a", microphone_confirmed=True)
    assert gate.observe_transcript(transcript, session_id="local-a") is False
    assert bus.snapshot()["published_total"] == 0


def test_wrong_session_cannot_trigger_or_disarm_current_session():
    gate, bus, _ = _gate()
    gate.arm(session_id="owner-session", microphone_confirmed=True)
    with pytest.raises(PermissionError):
        gate.arm(session_id="other", microphone_confirmed=True)
    with pytest.raises(PermissionError):
        gate.disarm(session_id="other")
    assert gate.observe_transcript("Hey Aura", session_id="other") is False
    assert gate.snapshot().session_id == "owner-session"
    assert bus.snapshot()["published_total"] == 0


def test_explicit_disarm_retires_session_and_blocks_old_transcripts():
    gate, bus, _ = _gate()
    gate.arm(session_id="owner-session", microphone_confirmed=True)
    snap = gate.disarm(session_id="owner-session")
    assert not snap.armed and not snap.session_id
    assert gate.observe_transcript("Hey Aura", session_id="owner-session") is False
    assert bus.snapshot()["published_total"] == 0


def test_each_activation_requires_rearm_and_respects_clock_cooldown():
    gate, bus, current = _gate()
    gate.arm(session_id="local-a", microphone_confirmed=True)
    assert gate.observe_transcript("Aura", session_id="local-a") is True
    gate.arm(session_id="local-a", microphone_confirmed=True)
    assert gate.observe_transcript("Aura", session_id="local-a") is False
    current["now"] = 101.5
    assert gate.observe_transcript("Aura", session_id="local-a") is False
    current["now"] = 102.0
    assert gate.observe_transcript("Aura", session_id="local-a") is True
    assert gate.snapshot().activation_count == 2
    assert bus.snapshot()["published_total"] == 2


def test_monotonic_clock_rollback_or_nonfinite_time_fails_closed():
    gate, bus, current = _gate()
    gate.arm(session_id="owner", microphone_confirmed=True)
    assert gate.observe_transcript("Aura", session_id="owner")
    gate.arm(session_id="owner", microphone_confirmed=True)
    for value in (99.0, float("nan"), float("inf")):
        current["now"] = value
        assert gate.observe_transcript("Aura", session_id="owner") is False
    assert bus.snapshot()["published_total"] == 1


@pytest.mark.parametrize("invalid", [
    "", " other ", "a\x00b", "a\nb", "x" * 129, "\ud800",
])
def test_malformed_session_rejected_before_any_event(invalid):
    gate, bus, _ = _gate()
    with pytest.raises(ValueError):
        gate.arm(session_id=invalid, microphone_confirmed=True)
    with pytest.raises(ValueError):
        gate.observe_transcript("Aura", session_id=invalid)
    assert bus.snapshot()["published_total"] == 0


def test_unsupported_clock_or_cooldown_rejected():
    with pytest.raises(TypeError):
        ConsentedWakeWordGate(object())
    for value in (True, -1, 0, 61, float("inf"), float("nan")):
        with pytest.raises(ValueError):
            ConsentedWakeWordGate(EventBus(), min_rearm_seconds=value)


def test_standard_unicode_normalization_without_new_authority():
    gate, bus, _ = _gate()
    gate.arm(session_id="local", microphone_confirmed=True)
    assert gate.observe_transcript("ＨＥＹ　ＡＵＲＡ！", session_id="local")
    assert bus.snapshot()["published_total"] == 1
