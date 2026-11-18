from __future__ import annotations

from aura_core.voice.metrics import VoiceLatencyMetrics
from aura_core.voice.sherpa_onnx import SherpaOnnxConfig


def test_sherpa_is_disabled_and_unavailable_without_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("AURA_NIRVANA_VOICE_ENABLED", raising=False)
    health = SherpaOnnxConfig.from_env().health()
    assert health["available"] is False
    assert health["reason"] == "disabled_by_feature_flag"


def test_latency_metrics_reports_nearest_rank_p50_and_p95():
    metrics = VoiceLatencyMetrics()
    for value in (10, 20, 30, 40, 50):
        metrics.record("tts_first_audio", value)
    assert metrics.snapshot()["tts_first_audio"] == {"count": 5, "p50_ms": 30.0, "p95_ms": 50.0}
