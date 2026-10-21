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
        "min_silence_duration_ms": 300,
        "speech_pad_ms": 400,
        "threshold": 0.45,
    }
    assert calls["condition_on_previous_text"] is True
    assert "Türkçe konuşma" in calls["initial_prompt"]
    assert calls["no_speech_threshold"] == 0.6
    assert calls["log_prob_threshold"] == -1.0
    assert calls["compression_ratio_threshold"] == 2.4

def test_default_stt_model_is_medium_and_prompt_can_be_configured(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    calls = {}

    class FakeModel:
        def __init__(self, model_name, **kwargs):
            calls["model_name"] = model_name
            calls["model_options"] = kwargs

        def transcribe(self, audio, **kwargs):
            calls["transcribe_options"] = kwargs
            return iter([]), SimpleNamespace(language="tr")

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeModel))
    monkeypatch.setattr(api_module, "_whisper_model", None)
    monkeypatch.delenv("AURA_STT_MODEL", raising=False)
    monkeypatch.setenv("AURA_STT_DEVICE", "cpu")
    monkeypatch.setenv("AURA_STT_COMPUTE_TYPE", "int8")
    monkeypatch.setenv("AURA_STT_INITIAL_PROMPT", "Türkçe komutlar: Doğa hakkında araştırma yap.")
    monkeypatch.setattr(api_module, "_stt_memory_store", False)

    text, language = api_module.transcribe_audio_bytes(b"fake-audio", "tr", ".wav")

    assert text == ""
    assert language == "tr"
    assert calls["model_name"] == "medium"
    assert calls["model_options"]["device"] == "cpu"
    assert calls["transcribe_options"]["initial_prompt"].startswith("Türkçe komutlar: Doğa hakkında araştırma yap.")
    monkeypatch.setattr(api_module, "_whisper_model", None)

def test_resolve_stt_runtime_selects_cuda_precision_when_available(monkeypatch) -> None:
    from types import SimpleNamespace

    monkeypatch.setenv("AURA_STT_DEVICE", "auto")
    monkeypatch.setenv("AURA_STT_COMPUTE_TYPE", "auto")
    monkeypatch.setitem(__import__("sys").modules, "ctranslate2", SimpleNamespace(get_cuda_device_count=lambda: 1))
    assert api_module.resolve_stt_runtime() == ("cuda", "float16")


def test_resolve_stt_runtime_uses_cpu_int8_when_cuda_unavailable(monkeypatch) -> None:
    from types import SimpleNamespace

    monkeypatch.setenv("AURA_STT_DEVICE", "auto")
    monkeypatch.setenv("AURA_STT_COMPUTE_TYPE", "auto")
    monkeypatch.setitem(__import__("sys").modules, "ctranslate2", SimpleNamespace(get_cuda_device_count=lambda: 0))
    assert api_module.resolve_stt_runtime() == ("cpu", "int8")


def test_explicit_cuda_without_device_fails_actionably(monkeypatch) -> None:
    from types import SimpleNamespace
    import pytest

    monkeypatch.setenv("AURA_STT_DEVICE", "cuda")
    monkeypatch.setenv("AURA_STT_COMPUTE_TYPE", "auto")
    monkeypatch.setitem(__import__("sys").modules, "ctranslate2", SimpleNamespace(get_cuda_device_count=lambda: 0))
    with pytest.raises(RuntimeError, match="CUDA was explicitly requested"):
        api_module.resolve_stt_runtime()

def test_context_prompt_failure_falls_back_to_static_turkish_prompt(monkeypatch) -> None:
    monkeypatch.setenv("AURA_STT_INITIAL_PROMPT", "Türkçe sabit istem.")
    monkeypatch.setattr(api_module, "_stt_memory_store", False)
    monkeypatch.setattr(api_module, "build_stt_prompt", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("context failure")))
    assert api_module._stt_context_prompt() == "Türkçe sabit istem."


def test_cuda_model_initialization_failure_retries_cpu_int8(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    calls = []

    class FakeModel:
        def __init__(self, model_name, **kwargs):
            calls.append(kwargs)
            if kwargs["device"] == "cuda":
                raise RuntimeError("missing CUDA runtime")

        def transcribe(self, audio, **kwargs):
            return iter([]), SimpleNamespace(language="tr")

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeModel))
    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(get_cuda_device_count=lambda: 1))
    monkeypatch.setenv("AURA_STT_DEVICE", "auto")
    monkeypatch.setenv("AURA_STT_COMPUTE_TYPE", "auto")
    monkeypatch.setattr(api_module, "_whisper_model", None)
    monkeypatch.setattr(api_module, "_whisper_model_device", None)
    monkeypatch.setattr(api_module, "_stt_memory_store", False)

    text, language = api_module.transcribe_audio_bytes(b"fake-audio", "tr", ".wav")

    assert (text, language) == ("", "tr")
    assert [call["device"] for call in calls] == ["cuda", "cpu"]
    assert calls[1]["compute_type"] == "int8"
    monkeypatch.setattr(api_module, "_whisper_model", None)
    monkeypatch.setattr(api_module, "_whisper_model_device", None)


def test_cuda_inference_failure_retries_recording_on_cpu(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    calls = []

    class Segment:
        text = "Türkçe yedek transkripsiyon"

    class FakeModel:
        def __init__(self, model_name, **kwargs):
            self.device = kwargs["device"]
            calls.append(("init", self.device))

        def transcribe(self, audio, **kwargs):
            calls.append(("transcribe", self.device))
            if self.device == "cuda":
                raise RuntimeError("CUDA inference failure")
            return iter([Segment()]), SimpleNamespace(language="tr")

    class BrokenContainerModule:
        @staticmethod
        def open(*args, **kwargs):
            raise RuntimeError("synthetic invalid container")

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeModel))
    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(get_cuda_device_count=lambda: 1))
    monkeypatch.setitem(sys.modules, "av", BrokenContainerModule)
    monkeypatch.setenv("AURA_STT_DEVICE", "auto")
    monkeypatch.setenv("AURA_STT_COMPUTE_TYPE", "auto")
    monkeypatch.setattr(api_module, "_whisper_model", None)
    monkeypatch.setattr(api_module, "_whisper_model_device", None)
    monkeypatch.setattr(api_module, "_stt_memory_store", False)

    text, language = api_module.transcribe_audio_bytes(b"synthetic-audio", "tr", ".wav")

    assert (text, language) == ("Türkçe yedek transkripsiyon", "tr")
    assert ("init", "cuda") in calls
    assert ("init", "cpu") in calls
    assert calls[-1] == ("transcribe", "cpu")
    monkeypatch.setattr(api_module, "_whisper_model", None)
    monkeypatch.setattr(api_module, "_whisper_model_device", None)

