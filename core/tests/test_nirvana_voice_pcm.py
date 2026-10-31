"""Provider isolation and bounded stream regressions."""
import asyncio
from types import SimpleNamespace
import numpy as np
import pytest
from aura_core.voice.sherpa_onnx import SherpaOnnxConfig, SherpaOnnxRecognizer


def test_separate_kws_asr_profiles(tmp_path, monkeypatch):
    paths = {
        "KWS_TOKENS": "kws/tokens.txt", "KWS_ENCODER": "kws/encoder.onnx",
        "KWS_DECODER": "kws/decoder.onnx", "KWS_JOINER": "kws/joiner.onnx",
        "KWS_KEYWORDS": "kws/keywords.txt", "ASR_TOKENS": "asr/tokens.txt",
        "ASR_ENCODER": "asr/encoder.onnx", "ASR_DECODER": "asr/decoder.onnx",
        "ASR_JOINER": "asr/joiner.onnx",
    }
    for key, name in paths.items():
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"test-asset")
        monkeypatch.setenv("AURA_SHERPA_" + key + "_PATH", str(file))
    monkeypatch.setenv("AURA_NIRVANA_VOICE_ENABLED", "1")
    monkeypatch.setenv("AURA_SHERPA_MODEL_LICENSE_ACCEPTED", "1")
    monkeypatch.setattr("aura_core.voice.sherpa_onnx.importlib.util.find_spec", lambda name: object())
    cfg = SherpaOnnxConfig.from_env()
    assert cfg.health()["available"]
    assert cfg.health()["kws_language"] == "en"
    assert cfg.kws_encoder_path != cfg.asr_encoder_path
    monkeypatch.setenv("AURA_SHERPA_ASR_ENCODER_PATH", str(cfg.kws_encoder_path))
    assert not SherpaOnnxConfig.from_env().health()["available"]


class Stream:
    def __init__(self):
        self.parts = []
    def accept_waveform(self, sample_rate, samples):
        assert sample_rate == 16000
        self.parts.append(samples.copy())
    def input_finished(self):
        pass


class KWS:
    def create_stream(self):
        return Stream()
    def is_ready(self, stream):
        return False
    def get_result(self, stream):
        return SimpleNamespace(keyword="AURA" if stream.parts else "")


class ASR:
    def create_stream(self):
        return Stream()
    def is_ready(self, stream):
        return False
    def get_result(self, stream):
        return SimpleNamespace(text="open calendar" if stream.parts else "")


def test_wake_audio_is_not_replayed_to_asr_and_pcm_is_validated():
    async def run():
        r = object.__new__(SherpaOnnxRecognizer)
        r._lock = asyncio.Lock()
        r._kws = KWS()
        r._asr = ASR()
        r._sessions = {}
        data = np.zeros(1600, dtype="<f4").tobytes()
        first = await r.consume_pcm(data, session_id="test")
        assert first["wake_detected"]
        assert r._sessions["test"]["asr_stream"].parts == []
        result = await r.consume_pcm(data, session_id="test", end=True)
        assert result["transcript"] == "open calendar"
        assert "test" not in r._sessions
        with pytest.raises(ValueError):
            await r.consume_pcm(b"bad", session_id="test")
        with pytest.raises(ValueError):
            await r.consume_pcm(np.full(1600, np.nan, dtype="<f4").tobytes(), session_id="test")
    asyncio.run(run())
