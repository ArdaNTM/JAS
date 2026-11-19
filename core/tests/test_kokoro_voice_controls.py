"""Kokoro MCP voice settings, error sanitization and bounded multi-chunk audio."""
import asyncio
import base64
import importlib.util
import json
import math
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from aura_core.tts.kokoro_guard import (
    SUPPORTED_ENGLISH_VOICES, validate_kokoro_voice_request,
)


def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "kokoro_tts_mcp.py"
    spec = importlib.util.spec_from_file_location("aura_kokoro_tts_test_service", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_valid_voice_rate_and_speech_cleanup():
    request = validate_kokoro_voice_request("Hello **AURA**!", "af_bella", 1.2)
    assert request.text == "Hello AURA!"
    assert request.voice == "af_bella"
    assert request.speed == 1.2
    assert len(SUPPORTED_ENGLISH_VOICES) >= 2


@pytest.mark.parametrize("voice", ["", "arbitrary", "../../model", "tr_TR", "am_wrong", 4])
def test_unknown_or_malformed_voice_fails_closed(voice):
    with pytest.raises(ValueError):
        validate_kokoro_voice_request("Hello", voice, 1.0)


@pytest.mark.parametrize("rate", [0, -1, 100, float("inf"), float("nan"), True, "fast", None])
def test_unsafe_rate_fails_closed(rate):
    with pytest.raises(ValueError):
        validate_kokoro_voice_request("Hello", "af_heart", rate)


@pytest.mark.parametrize("content", ["", " ", "x" * 4001, None, 8, "https://example.invalid/"])
def test_missing_unsafe_or_url_only_text_fails_before_model_loading(content):
    with pytest.raises(ValueError):
        validate_kokoro_voice_request(content, "af_heart", 1.0)


def test_kokoro_synthesizer_processes_every_chunk_with_mocked_local_model(monkeypatch):
    seen = []
    class FakePipeline:
        def __init__(self, *, lang_code):
            assert lang_code == "a"
        def __call__(self, text, *, voice, speed):
            seen.append((text, voice, speed))
            yield SimpleNamespace(audio=[0.1] * 12)
            yield SimpleNamespace(audio=[0.2] * 16)

    class FakeSoundFile:
        def __init__(self, buffer, **kwargs):
            self.buffer = buffer
            assert kwargs["samplerate"] == 24000
            assert kwargs["channels"] == 1
            self.buffer.write(b"RIFF")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def write(self, audio):
            self.buffer.write(bytes([len(audio)]))
    monkeypatch.setitem(sys.modules, "kokoro", SimpleNamespace(KPipeline=FakePipeline))
    monkeypatch.setitem(sys.modules, "soundfile", SimpleNamespace(SoundFile=FakeSoundFile))
    script = _load_script()
    result = script.synthesize("Hello world.", "af_bella", 0.8)
    assert seen == [("Hello world.", "af_bella", 0.8)]
    assert base64.b64decode(result["audio_base64"]) == b"RIFF\x0c\x10"
    assert result["mime_type"] == "audio/wav"
    assert result["voice"] == "af_bella"


def test_audio_over_max_duration_fails_without_unbounded_processing(monkeypatch):
    class HugePipeline:
        def __init__(self, *, lang_code): pass
        def __call__(self, *args, **kwargs):
            yield SimpleNamespace(audio=range(24_000 * 90 + 1))
    class FakeSoundFile:
        def __init__(self, buffer, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def write(self, audio): raise AssertionError("oversized audio must not be written")
    monkeypatch.setitem(sys.modules, "kokoro", SimpleNamespace(KPipeline=HugePipeline))
    monkeypatch.setitem(sys.modules, "soundfile", SimpleNamespace(SoundFile=FakeSoundFile))
    with pytest.raises(RuntimeError, match="bounded audio duration"):
        _load_script().synthesize("Hello", "af_heart", 1.0)


def test_mcp_schema_closes_additional_arguments():
    script = _load_script()
    result = asyncio.run(script.handle_list_tools(None, None))
    schema = result.tools[0].input_schema
    assert schema["additionalProperties"] is False
    assert schema["properties"]["text"]["maxLength"] == 4000
    assert schema["properties"]["voice"]["enum"] == list(SUPPORTED_ENGLISH_VOICES)
    assert schema["properties"]["speed"]["minimum"] == 0.75


def test_mcp_error_response_does_not_expose_attacker_input():
    import mcp.types as types
    script = _load_script()
    fake_secret = "SECRET_UNTRUSTED_TEXT/../../private"
    params = types.CallToolRequestParams(
        name="synthesize",
        arguments={"text": fake_secret, "voice": "not-a-voice", "speed": 1.0},
    )
    result = asyncio.run(script.handle_call_tool(None, params))
    assert result.is_error is True
    assert "ValueError" in result.content[0].text
    assert fake_secret not in result.content[0].text


def test_executable_kokoro_provider_is_in_final_release_inventory():
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads((root / "release-manifest.final.json").read_text(encoding="utf-8"))
    locked = {item["path"] for item in manifest["files"]}
    assert "core/src/aura_core/tts/kokoro_guard.py" in locked
    assert "core/scripts/kokoro_tts_mcp.py" in locked
