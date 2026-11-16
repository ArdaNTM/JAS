"""PCM16 ambient signal safety, consent lifecycle and no-data EventBus projection."""
import asyncio
import struct

import pytest

from aura_core.application.ambient_signal import (
    ConsentedAmbientSignalObserver, analyze_pcm16_signal,
)
from aura_core.kernel.events import EventBus


def _pcm(value, count=1600):
    return struct.pack("<" + "h" * count, *([value] * count))


def test_bounded_quiet_activity_clipping_signal_metrics():
    quiet = analyze_pcm16_signal(_pcm(0))
    active = analyze_pcm16_signal(_pcm(4000))
    clipped = analyze_pcm16_signal(_pcm(32767))
    assert quiet.level == "quiet" and quiet.rms == 0
    assert active.level == "activity" and 0.1 < active.rms < 0.13
    assert clipped.level == "clipping" and clipped.clipped_fraction == 1.0
    assert active.duration_ms == 100
    assert all(metric.classification == "SIGNAL_ENERGY_ONLY_NOT_SOUND_IDENTITY"
               for metric in (quiet, active, clipped))


@pytest.mark.parametrize("audio", [
    b"", b"\x00", b"\x00\x00" * 159, b"\x00\x00" * 32001,
    b"\x00\x00" * 160 + b"\x00", bytearray(b"\x00" * 320), "no", None,
])
def test_invalid_or_unbounded_audio_rejected(audio):
    with pytest.raises(ValueError):
        analyze_pcm16_signal(audio)


@pytest.mark.parametrize("rate", [0, 8000, 44100, "16000", True, None])
def test_nonmatching_sample_rate_is_not_guessed(rate):
    with pytest.raises(ValueError):
        analyze_pcm16_signal(_pcm(100), sample_rate=rate)


def test_consent_is_required_before_any_metrics_or_event_publication():
    bus = EventBus()
    observer = ConsentedAmbientSignalObserver(bus)
    for confirmed in (False, 1, None, "true"):
        with pytest.raises(PermissionError):
            observer.start(session_id="local", microphone_confirmed=confirmed)
    with pytest.raises(PermissionError):
        observer.observe(_pcm(2000), session_id="local")
    assert bus.snapshot()["published_total"] == 0


def test_events_only_on_coarse_changes_and_contain_no_raw_audio():
    bus = EventBus()
    seen = []
    bus.subscribe("AmbientSignalLevelChanged", lambda e: seen.append(e))
    observer = ConsentedAmbientSignalObserver(bus)
    observer.start(session_id="local", microphone_confirmed=True)
    observer.observe(_pcm(0), session_id="local")
    observer.observe(_pcm(0), session_id="local")
    observer.observe(_pcm(4000), session_id="local")
    observer.observe(_pcm(32767), session_id="local")
    assert bus.snapshot()["published_total"] == 3
    for _ in range(3):
        assert asyncio.run(bus.dispatch_once())
    assert [e.payload["level"] for e in seen] == ["quiet", "activity", "clipping"]
    assert all(e.source_component == "aura.ambient_signal" for e in seen)
    assert all("audio" not in e.payload and "samples" not in e.payload for e in seen)
    assert all(e.payload["classification"] == "SIGNAL_ENERGY_ONLY_NOT_SOUND_IDENTITY" for e in seen)
    assert all(e.session_id == "local" for e in seen)


def test_session_isolation_and_stop_revoke_observation():
    bus = EventBus()
    observer = ConsentedAmbientSignalObserver(bus)
    observer.start(session_id="a", microphone_confirmed=True)
    with pytest.raises(PermissionError):
        observer.start(session_id="b", microphone_confirmed=True)
    with pytest.raises(PermissionError):
        observer.observe(_pcm(0), session_id="b")
    with pytest.raises(PermissionError):
        observer.stop(session_id="b")
    observer.stop(session_id="a")
    with pytest.raises(PermissionError):
        observer.observe(_pcm(0), session_id="a")
    assert bus.snapshot()["published_total"] == 0


def test_stop_during_pcm_analysis_suppresses_stale_event_and_result(monkeypatch):
    import aura_core.application.ambient_signal as module
    bus = EventBus()
    observer = ConsentedAmbientSignalObserver(bus)
    observer.start(session_id="a", microphone_confirmed=True)
    original = module.analyze_pcm16_signal

    def stop_during_analysis(audio):
        observer.stop(session_id="a")
        return original(audio)

    monkeypatch.setattr(module, "analyze_pcm16_signal", stop_during_analysis)
    with pytest.raises(PermissionError, match="expired"):
        observer.observe(_pcm(4000), session_id="a")
    assert bus.snapshot()["published_total"] == 0


@pytest.mark.parametrize("invalid", ["", " x", "a\nb", "a\x00b", "x" * 129, "\ud800"])
def test_session_identifiers_are_strictly_validated(invalid):
    observer = ConsentedAmbientSignalObserver(EventBus())
    with pytest.raises(ValueError):
        observer.start(session_id=invalid, microphone_confirmed=True)


def test_only_existing_kernel_event_bus_can_be_used():
    with pytest.raises(TypeError):
        ConsentedAmbientSignalObserver(object())
