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
