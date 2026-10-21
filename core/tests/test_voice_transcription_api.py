import base64

from fastapi.testclient import TestClient

from aura_core.application import api as api_module
from aura_core.application.api import create_api
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig


def make_client() -> TestClient:
    config = RuntimeConfig(
        runtime="ollama",
        model="qwen3:4b-instruct-2507-q4_K_M",
        temperature=0.7,
        max_tokens=32,
    )
    backend = BackendConfig(
        endpoint="http://127.0.0.1:11434",
        timeout=30.0,
    )
    return TestClient(create_api(config, backend_config=backend))


def test_local_speech_transcription_returns_transcript(monkeypatch) -> None:
    calls = {}

    def fake_transcribe(audio_bytes: bytes, language: str, suffix: str):
        calls.update(audio_bytes=audio_bytes, language=language, suffix=suffix)
        return "Merhaba AURA", "tr"

    monkeypatch.setattr(api_module, "transcribe_audio_bytes", fake_transcribe)
    response = make_client().post(
        "/api/speech/transcribe",
        json={
            "audio_base64": base64.b64encode(b"test-audio").decode("ascii"),
            "mime_type": "audio/webm;codecs=opus",
            "language": "tr",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"text": "Merhaba AURA", "language": "tr"}
    assert calls == {
        "audio_bytes": b"test-audio",
        "language": "tr",
        "suffix": ".webm",
    }


def test_local_speech_transcription_rejects_invalid_base64() -> None:
    response = make_client().post(
        "/api/speech/transcribe",
        json={"audio_base64": "%%%invalid%%%", "mime_type": "audio/webm"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid base64 audio payload"


def test_local_speech_transcription_rejects_unsupported_mime() -> None:
    response = make_client().post(
        "/api/speech/transcribe",
        json={
            "audio_base64": base64.b64encode(b"audio").decode("ascii"),
            "mime_type": "application/octet-stream",
        },
    )

    assert response.status_code == 415
    assert response.json()["detail"] == "Unsupported audio format"



def test_local_speech_transcription_500_returns_safe_structured_diagnostic(monkeypatch) -> None:
    def fail_transcription(audio_bytes: bytes, language: str, suffix: str):
        raise RuntimeError("synthetic failure containing a private path")

    monkeypatch.setattr(api_module, "transcribe_audio_bytes", fail_transcription)
    response = make_client().post(
        "/api/speech/transcribe",
        headers={"X-Request-ID": "voice-test-request-500"},
        json={
            "audio_base64": base64.b64encode(b"test-audio").decode("ascii"),
            "mime_type": "audio/webm",
            "language": "tr",
        },
    )

    payload = response.json()
    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "voice-test-request-500"
    assert payload["error"]["code"] == "stt_internal_error"
    assert payload["error"]["request_id"] == "voice-test-request-500"
    assert payload["error"]["details"] == {"exception_type": "RuntimeError"}
    assert "request ID" in payload["error"]["message"]
    assert "private path" not in response.text
    assert "synthetic failure" not in response.text


def test_local_speech_transcription_model_load_failure_is_actionable(monkeypatch) -> None:
    def fail_model_load(audio_bytes: bytes, language: str, suffix: str):
        raise api_module.SpeechModelLoadError("underlying details are logged only")

    monkeypatch.setattr(api_module, "transcribe_audio_bytes", fail_model_load)
    response = make_client().post(
        "/api/speech/transcribe",
        json={
            "audio_base64": base64.b64encode(b"test-audio").decode("ascii"),
            "mime_type": "audio/webm",
            "language": "tr",
        },
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "stt_model_load_failed"
    assert "AURA_STT_MODEL" in response.json()["error"]["message"]
    assert response.json()["error"]["details"] == {"exception_type": "SpeechModelLoadError"}


def test_local_speech_transcription_engine_failure_is_actionable(monkeypatch) -> None:
    def fail_decode(audio_bytes: bytes, language: str, suffix: str):
        raise api_module.SpeechTranscriptionError("runtime details are logged only")

    monkeypatch.setattr(api_module, "transcribe_audio_bytes", fail_decode)
    response = make_client().post(
        "/api/speech/transcribe",
        json={
            "audio_base64": base64.b64encode(b"test-audio").decode("ascii"),
            "mime_type": "audio/webm;codecs=opus",
            "language": "tr",
        },
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "stt_transcription_failed"
    assert "codec/container" in response.json()["error"]["message"]
    assert "runtime details" not in response.text


def test_local_speech_transcription_accepts_m4a_alias(monkeypatch) -> None:
    calls = {}

    def fake_transcribe(audio_bytes: bytes, language: str, suffix: str):
        calls["suffix"] = suffix
        return "Merhaba", "tr"

    monkeypatch.setattr(api_module, "transcribe_audio_bytes", fake_transcribe)
    response = make_client().post(
        "/api/speech/transcribe",
        json={
            "audio_base64": base64.b64encode(b"test-audio").decode("ascii"),
            "mime_type": "audio/x-m4a; codecs=mp4a.40.2",
            "language": "tr",
        },
    )

    assert response.status_code == 200
    assert calls["suffix"] == ".m4a"

def test_transcription_uses_quality_oriented_decode_options(monkeypatch) -> None:
    calls = {}

    class FakeSegment:
        text = "Doğa hakkında araştırma yap"

    class FakeInfo:
        language = "tr"

    class FakeModel:
        def transcribe(self, audio, **kwargs):
            calls.update(kwargs)
            return iter([FakeSegment()]), FakeInfo()

    monkeypatch.setattr(api_module, "_whisper_model", FakeModel())
    monkeypatch.setenv("AURA_STT_BEAM_SIZE", "5")

    text, language = api_module.transcribe_audio_bytes(
        b"synthetic-audio-bytes",
        language="tr",
        suffix=".wav",
    )

    assert text == "Doğa hakkında araştırma yap"
    assert language == "tr"
    assert calls["language"] == "tr"
    assert calls["beam_size"] == 5
    assert calls["temperature"] == 0.0
    assert calls["vad_filter"] is True
    assert calls["vad_parameters"] == {
        "min_silence_duration_ms": 350,
        "speech_pad_ms": 250,
    }
    assert calls["condition_on_previous_text"] is False

