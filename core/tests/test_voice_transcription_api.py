import base64
import io
import wave

import pytest
from aura_core.application import full_duplex_session as whisper

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
    app = create_api(config, backend_config=backend)
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "local_owner"
    return TestClient(app, headers={"Authorization": "Bearer " + "t" * 40})


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

@pytest.fixture(autouse=True)
def isolate_stt_runtime(monkeypatch):
    # No test shares a cached native model, live Owner configuration, or GPU latch.
    monkeypatch.setattr(whisper, "_shared_whisper", None)
    for name in ("AURA_STT_MODEL", "AURA_STT_CPU_MODEL", "AURA_STT_MODEL_PATH",
                 "AURA_STT_INITIAL_PROMPT", "AURA_STT_CPU_THREADS"):
        monkeypatch.delenv(name, raising=False)
    for name, value in {
        "AURA_STT_DEVICE": "auto",
        "AURA_STT_COMPUTE_TYPE": "auto",
        "AURA_VOICE_MODE": "standard",
        "AURA_STORAGE_MODE": "local",
        "AURA_EVOLUTION_REVIEW_ENABLED": "0",
        "AURA_EVOLUTION_SELF_PATCH_ENABLED": "0",
        "AURA_EVOLUTION_INTROSPECTION_ENABLED": "0",
        "AURA_BACKGROUND_THINKING_ENABLED": "0",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(api_module, "_stt_memory_store", False)


def _wav_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(48000)
        stream.writeframes(b"\x00\x00" * 4800 * 2)
    return buffer.getvalue()


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

    recognizer = whisper.shared_whisper_recognizer()
    monkeypatch.setattr(recognizer, "_model", FakeModel())
    monkeypatch.setattr(recognizer, "_active_device", "cpu")
    monkeypatch.setenv("AURA_STT_BEAM_SIZE", "5")

    text, language = api_module.transcribe_audio_bytes(
        _wav_bytes(),
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

def test_default_cpu_stt_model_is_small_and_prompt_can_be_configured(monkeypatch) -> None:
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
    monkeypatch.delenv("AURA_STT_MODEL", raising=False)
    monkeypatch.setenv("AURA_STT_DEVICE", "cpu")
    monkeypatch.setenv("AURA_STT_COMPUTE_TYPE", "int8")
    monkeypatch.setenv("AURA_STT_INITIAL_PROMPT", "Türkçe komutlar: Doğa hakkında araştırma yap.")
    monkeypatch.setattr(api_module, "_stt_memory_store", False)

    text, language = api_module.transcribe_audio_bytes(_wav_bytes(), "tr", ".wav")

    assert text == ""
    assert language == "tr"
    assert calls["model_name"] == "small"
    assert calls["model_options"]["device"] == "cpu"
    assert calls["transcribe_options"]["initial_prompt"].startswith("Türkçe komutlar: Doğa hakkında araştırma yap.")

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
    monkeypatch.setattr(api_module, "_stt_memory_store", False)

    text, language = api_module.transcribe_audio_bytes(_wav_bytes(), "tr", ".wav")

    assert (text, language) == ("", "tr")
    assert [call["device"] for call in calls] == ["cuda", "cpu"]
    assert calls[1]["compute_type"] == "int8"


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

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeModel))
    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(get_cuda_device_count=lambda: 1))
    monkeypatch.setenv("AURA_STT_DEVICE", "auto")
    monkeypatch.setenv("AURA_STT_COMPUTE_TYPE", "auto")
    monkeypatch.setattr(api_module, "_stt_memory_store", False)

    text, language = api_module.transcribe_audio_bytes(_wav_bytes(), "tr", ".wav")

    assert (text, language) == ("Türkçe yedek transkripsiyon", "tr")
    assert ("init", "cuda") in calls
    assert ("init", "cpu") in calls
    assert calls[-1] == ("transcribe", "cpu")
    assert api_module.transcribe_audio_bytes(_wav_bytes(), "tr", ".wav") == (text, language)
    assert calls == [("init", "cuda"), ("transcribe", "cuda"), ("init", "cpu"), ("transcribe", "cpu"), ("transcribe", "cpu")]

def test_explicit_unavailable_cuda_configuration_still_uses_cpu(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    initialized_devices = []

    class FakeModel:
        def __init__(self, model_name, **kwargs):
            initialized_devices.append((kwargs["device"], kwargs["compute_type"]))

        def transcribe(self, audio, **kwargs):
            return iter([]), SimpleNamespace(language="tr")

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeModel))
    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(get_cuda_device_count=lambda: 0))
    monkeypatch.setenv("AURA_STT_DEVICE", "cuda")
    monkeypatch.setenv("AURA_STT_COMPUTE_TYPE", "float16")
    monkeypatch.setattr(api_module, "_stt_memory_store", False)

    assert api_module.transcribe_audio_bytes(_wav_bytes(), "tr", ".wav") == ("", "tr")
    assert initialized_devices == [("cpu", "int8")]

@pytest.mark.parametrize("container_format", ["webm", "ogg", "wav"])
def test_real_browser_containers_decode_to_mono_float32(container_format):
    import av
    import numpy as np

    if container_format == "wav":
        data = _wav_bytes()
    else:
        buffer = io.BytesIO()
        with av.open(buffer, mode="w", format=container_format) as output:
            stream = output.add_stream("libopus", rate=48000)
            stream.layout = "mono"
            frame = av.AudioFrame.from_ndarray(
                np.zeros((1, 4800), dtype=np.float32), format="fltp", layout="mono"
            )
            frame.sample_rate = 48000
            for packet in stream.encode(frame):
                output.mux(packet)
            for packet in stream.encode(None):
                output.mux(packet)
        data = buffer.getvalue()
    samples = whisper.FasterWhisperRecognizer._decode_audio(data)
    assert samples.dtype == np.float32
    assert samples.ndim == 1
    assert 1400 <= samples.size <= 1800
    assert np.isfinite(samples).all()


def test_codec_failure_does_not_load_or_retry_cuda(monkeypatch):
    import sys
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(
        WhisperModel=lambda *args, **kwargs: pytest.fail("invalid codec must not load a model")
    ))
    with pytest.raises(api_module.SpeechDecodeError):
        api_module.transcribe_audio_bytes(b"not an audio container", "tr")
    assert whisper.shared_whisper_recognizer()._cpu_only is False


def test_http_and_full_duplex_share_cpu_fallback_model(monkeypatch):
    import asyncio
    import sys
    from types import SimpleNamespace

    models, calls, decoded = [], [], []
    monkeypatch.setenv("AURA_STT_CPU_MODEL", "tiny")
    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(get_cuda_device_count=lambda: 1))

    class Model:
        def __init__(self, name, *, device, compute_type, cpu_threads):
            models.append((name, device, compute_type))
            self.device = device

        def transcribe(self, samples, **kwargs):
            calls.append((self.device, samples))
            def segments():
                if self.device == "cuda":
                    raise RuntimeError("native runtime unavailable")
                yield SimpleNamespace(text="Merhaba")
            return segments(), SimpleNamespace(language="tr")

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Model))
    recognizer = whisper.shared_whisper_recognizer()
    def decode(payload):
        samples = object()
        decoded.append(samples)
        return samples
    monkeypatch.setattr(recognizer, "_decode_audio", decode)
    assert api_module.transcribe_audio_bytes(b"first", "tr") == ("Merhaba", "tr")
    assert asyncio.run(whisper.shared_whisper_recognizer().transcribe(b"second", session_id="voice")) == "Merhaba"
    assert models == [("small", "cuda", "float16"), ("tiny", "cpu", "int8")]
    assert [device for device, _ in calls] == ["cuda", "cpu", "cpu"]
    assert calls[0][1] is calls[1][1] is decoded[0]
    assert calls[2][1] is decoded[1]
    assert len(decoded) == 2
