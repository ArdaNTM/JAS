from __future__ import annotations
import json
from pathlib import Path
import pytest
from aura_core.tts.offline_voice import OfflineVoiceConfig


def prepare(tmp_path: Path):
    stt = tmp_path / "whisper"
    stt.mkdir()
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (stt / name).write_bytes(b"local-model")
    piper = tmp_path / "voice.onnx"
    piper.write_bytes(b"local-onnx")
    config = Path(str(piper) + ".json")
    config.write_text(json.dumps({"language": {"code": "tr_TR"}}), encoding="utf-8")
    return stt, piper, config


def env(stt, piper, config):
    return {
        "AURA_VOICE_MODE": "offline",
        "AURA_TTS_PROVIDER": "piper",
        "AURA_STT_MODEL_PATH": str(stt),
        "AURA_PIPER_MODEL_PATH": str(piper),
        "AURA_PIPER_CONFIG_PATH": str(config),
    }


def test_standard_voice_mode_is_unchanged():
    assert OfflineVoiceConfig.from_environment({"AURA_VOICE_MODE": "standard"}) is None


def test_offline_mode_requires_local_piper_provider(tmp_path):
    stt, piper, config = prepare(tmp_path)
    values = env(stt, piper, config)
    values["AURA_TTS_PROVIDER"] = "kokoro"
    with pytest.raises(ValueError, match="piper"):
        OfflineVoiceConfig.from_environment(values)


def test_offline_mode_requires_absolute_existing_stt_directory(tmp_path):
    stt, piper, config = prepare(tmp_path)
    values = env(stt, piper, config)
    values["AURA_STT_MODEL_PATH"] = "relative/model"
    with pytest.raises(ValueError, match="absolute"):
        OfflineVoiceConfig.from_environment(values)


def test_offline_mode_rejects_incomplete_whisper_model(tmp_path):
    stt, piper, config = prepare(tmp_path)
    (stt / "tokenizer.json").unlink()
    values = env(stt, piper, config)
    with pytest.raises(ValueError, match="tokenizer"):
        OfflineVoiceConfig.from_environment(values)


def test_offline_mode_requires_local_turkish_piper_assets(tmp_path):
    stt, piper, config = prepare(tmp_path)
    values = env(stt, piper, config)
    actual = OfflineVoiceConfig.from_environment(values)
    assert actual is not None
    assert actual.stt_model_path == str(stt.resolve())
    assert actual.piper_model_path == str(piper.resolve())
    assert actual.piper_config_path == str(config.resolve())


def test_offline_mode_rejects_non_turkish_voice(tmp_path):
    stt, piper, config = prepare(tmp_path)
    config.write_text(json.dumps({"language": {"code": "en_US"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="Turkish"):
        OfflineVoiceConfig.from_environment(env(stt, piper, config))


def test_offline_mode_fails_closed_when_assets_are_missing(tmp_path):
    stt, piper, config = prepare(tmp_path)
    values = env(stt, piper, config)
    values["AURA_PIPER_MODEL_PATH"] = str(tmp_path / "missing.onnx")
    with pytest.raises(FileNotFoundError):
        OfflineVoiceConfig.from_environment(values)
