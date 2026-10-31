"""Piper's Turkish voice stays local, cached, and MCP structured."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


def load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "piper_tts_mcp.py"
    spec = importlib.util.spec_from_file_location("_test_piper_mcp", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_turkish_voice_is_cached_and_audio_is_structured(monkeypatch, tmp_path):
    script = load_script()
    model = tmp_path / "tr_TR-dfki-medium.onnx"
    model.write_bytes(b"fake-onnx-test")
    config = tmp_path / "tr_TR-dfki-medium.onnx.json"
    config.write_text(json.dumps({"language": {"code": "tr_TR"}}), encoding="utf-8")
    monkeypatch.setenv("AURA_PIPER_MODEL_PATH", str(model))
    monkeypatch.setenv("AURA_PIPER_CONFIG_PATH", str(config))
    counts = {"loads": 0, "synthesis": 0}

    class FakePiperVoice:
        @classmethod
        def load(cls, model_path, config_path):
            counts["loads"] += 1
            assert model_path == str(model)
            assert config_path == str(config)
            return cls()

        def synthesize_wav(self, text, wav_file, syn_config=None):
            assert syn_config is not None
            assert 0.7 <= syn_config.length_scale <= 1.6
            counts["synthesis"] += 1
            assert text == "Merhaba AURA"
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            wav_file.writeframes(b"\0\0" * 16)

    class FakeSynthesisConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    monkeypatch.setitem(sys.modules, "piper", SimpleNamespace(
        PiperVoice=FakePiperVoice, SynthesisConfig=FakeSynthesisConfig,
    ))
    request = SimpleNamespace(name="synthesize", arguments={"text": "Merhaba AURA"})
    one = asyncio.run(script.handle_call_tool(None, request))
    two = asyncio.run(script.handle_call_tool(None, request))
    assert not one.is_error
    assert one.structured_content["mime_type"] == "audio/wav"
    assert one.structured_content["provider"] == "piper"
    assert one.structured_content["audio_base64"] == two.structured_content["audio_base64"]
    assert counts == {"loads": 1, "synthesis": 2}


def test_english_voice_is_rejected_even_with_valid_files(monkeypatch, tmp_path):
    script = load_script()
    model = tmp_path / "english.onnx"
    model.write_bytes(b"fake")
    (tmp_path / "english.onnx.json").write_text(
        json.dumps({"language": {"code": "en_US"}}), encoding="utf-8"
    )
    monkeypatch.setenv("AURA_PIPER_MODEL_PATH", str(model))
    monkeypatch.delenv("AURA_PIPER_CONFIG_PATH", raising=False)
    reply = asyncio.run(script.handle_call_tool(
        None, SimpleNamespace(name="synthesize", arguments={"text": "Merhaba"})
    ))
    assert reply.is_error
    assert reply.structured_content is None
    assert "english.onnx" not in reply.content[0].text


def test_piper_requires_explicit_local_model(monkeypatch):
    script = load_script()
    monkeypatch.delenv("AURA_PIPER_MODEL_PATH", raising=False)
    try:
        script._voice_paths()
    except RuntimeError as exc:
        assert "AURA_PIPER_MODEL_PATH" in str(exc)
    else:
        raise AssertionError("Unconfigured Piper must fail closed")
