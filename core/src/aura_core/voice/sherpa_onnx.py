"""Independent sherpa-onnx KWS and streaming transducer ASR.

Only owner-provisioned models are accepted. Input is float32 mono PCM at
16kHz, in bounded 100ms chunks. KWS never feeds its wake audio back into ASR.
No remote calls or automatic model downloads occur in the provider.
"""
from __future__ import annotations

import asyncio
import importlib.util
import io
import os
import time
import numpy as np
from dataclasses import dataclass
from pathlib import Path


def _path(key: str) -> Path | None:
    value = os.getenv(key, "").strip()
    return Path(value).expanduser() if value else None


@dataclass(frozen=True, slots=True)
class SherpaOnnxConfig:
    enabled: bool
    license_accepted: bool
    kws_tokens_path: Path | None
    kws_encoder_path: Path | None
    kws_decoder_path: Path | None
    kws_joiner_path: Path | None
    kws_keywords_path: Path | None
    asr_tokens_path: Path | None
    asr_encoder_path: Path | None
    asr_decoder_path: Path | None
    asr_joiner_path: Path | None

    @classmethod
    def from_env(cls) -> "SherpaOnnxConfig":
        return cls(
            enabled=os.getenv("AURA_NIRVANA_VOICE_ENABLED", "0").strip().lower() in {"1", "true", "yes"},
            license_accepted=os.getenv("AURA_SHERPA_MODEL_LICENSE_ACCEPTED", "0") == "1",
            kws_tokens_path=_path("AURA_SHERPA_KWS_TOKENS_PATH"),
            kws_encoder_path=_path("AURA_SHERPA_KWS_ENCODER_PATH"),
            kws_decoder_path=_path("AURA_SHERPA_KWS_DECODER_PATH"),
            kws_joiner_path=_path("AURA_SHERPA_KWS_JOINER_PATH"),
            kws_keywords_path=_path("AURA_SHERPA_KWS_KEYWORDS_PATH"),
            asr_tokens_path=_path("AURA_SHERPA_ASR_TOKENS_PATH"),
            asr_encoder_path=_path("AURA_SHERPA_ASR_ENCODER_PATH"),
            asr_decoder_path=_path("AURA_SHERPA_ASR_DECODER_PATH"),
            asr_joiner_path=_path("AURA_SHERPA_ASR_JOINER_PATH"),
        )

    def health(self) -> dict[str, object]:
        keys = ("kws_tokens", "kws_encoder", "kws_decoder", "kws_joiner",
                "kws_keywords", "asr_tokens", "asr_encoder", "asr_decoder", "asr_joiner")
        missing = [key for key in keys
                   if (path := getattr(self, key + "_path")) is None or not path.is_file()]
        package = importlib.util.find_spec("sherpa_onnx") is not None
        # A KWS model is NOT interchangeable with an ASR model.
        same = (self.kws_encoder_path is not None and
                self.kws_encoder_path == self.asr_encoder_path)
        ready = self.enabled and self.license_accepted and package and not missing and not same
        if not self.enabled:
            reason = "disabled_by_feature_flag"
        elif not self.license_accepted:
            reason = "model_license_not_acknowledged"
        elif not package:
            reason = "python_package_unavailable"
        elif missing:
            reason = "model_files_unavailable"
        elif same:
            reason = "kws_and_asr_models_must_be_separate"
        else:
            reason = "ready"
        return {"provider": "sherpa-onnx", "enabled": self.enabled, "available": ready,
                "reason": reason, "missing": missing, "license_acknowledged": self.license_accepted,
                "kws_language": "en", "asr_language": "en", "sample_rate": 16000,
                "pcm_chunk_ms": 100, "wake_phrase": "AURA"}


class SherpaOnnxRecognizer:
    def __init__(self, config: SherpaOnnxConfig) -> None:
        health = config.health()
        if not health["available"]:
            raise RuntimeError("sherpa-onnx unavailable: " + str(health["reason"]))
        self._config = config
        self._lock = asyncio.Lock()
        self._kws = None
        self._asr = None
        self._sessions: dict[str, dict] = {}

    def _load(self) -> None:
        import sherpa_onnx
        c = self._config
        self._kws = sherpa_onnx.KeywordSpotter(
            tokens=str(c.kws_tokens_path), encoder=str(c.kws_encoder_path),
            decoder=str(c.kws_decoder_path), joiner=str(c.kws_joiner_path),
            keywords_file=str(c.kws_keywords_path), num_threads=1,
            sample_rate=16000, feature_dim=80, provider="cpu",
        )
        self._asr = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=str(c.asr_tokens_path), encoder=str(c.asr_encoder_path),
            decoder=str(c.asr_decoder_path), joiner=str(c.asr_joiner_path),
            num_threads=1, sample_rate=16000, feature_dim=80,
            decoding_method="greedy_search", provider="cpu",
        )

    def _feed(self, session_id: str, samples: np.ndarray, end: bool) -> dict[str, object]:
        if self._kws is None:
            self._load()
        state = self._sessions.get(session_id)
        if state is None:
            if len(self._sessions) >= 4:
                raise RuntimeError("Too many active recognition sessions")
            state = {"wake": False, "kws_stream": self._kws.create_stream(), "asr_stream": None}
            self._sessions[session_id] = state
        if state["wake"] and state.get("armed_until", 0) < time.monotonic():
            state = {"wake": False, "kws_stream": self._kws.create_stream(), "asr_stream": None}
            self._sessions[session_id] = state
        wake_detected = False
        transcript = ""
        if not state["wake"]:
            kws_stream = state["kws_stream"]
            if samples.size:
                kws_stream.accept_waveform(16000, samples)
            while self._kws.is_ready(kws_stream):
                self._kws.decode_stream(kws_stream)
            keyword = str(self._kws.get_result(kws_stream).keyword).strip()
            if keyword:
                state["wake"] = True
                state["asr_stream"] = self._asr.create_stream()
                wake_detected = True
                # Never replay wake-word samples as a command: avoids ASR echo.
        else:
            asr_stream = state["asr_stream"]
            if samples.size:
                asr_stream.accept_waveform(16000, samples)
            if end:
                asr_stream.input_finished()
            while self._asr.is_ready(asr_stream):
                self._asr.decode_stream(asr_stream)
            transcript = str(self._asr.get_result(asr_stream).text).strip()[:8000]
        if wake_detected:
            state["armed_until"] = time.monotonic() + 10
        if end:
            if state["wake"] and not transcript and time.monotonic() < state.get("armed_until", 0):
                # Wake-only utterance: retain authorization-free listening for a
                # bounded time, but use a fresh ASR stream for the next phrase.
                state["asr_stream"] = self._asr.create_stream()
            else:
                self._sessions.pop(session_id, None)
        return {"wake_detected": wake_detected, "transcript": transcript,
                "listening": bool(state["wake"]), "complete": end}

    async def consume_pcm(self, payload: bytes, *, session_id: str, end: bool = False) -> dict[str, object]:
        if not session_id or len(session_id) > 128 or len(payload) > 6400 or len(payload) % 4:
            raise ValueError("Invalid bounded PCM chunk")
        if not payload and not end:
            raise ValueError("PCM chunk must not be empty")
        samples = np.frombuffer(payload, dtype="<f4")
        if not np.all(np.isfinite(samples)) or np.any(np.abs(samples) > 1.25):
            raise ValueError("PCM samples out of range")
        async with self._lock:
            return await asyncio.to_thread(self._feed, session_id, samples.copy(), end)

    async def close_session(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)

    async def transcribe(self, audio: bytes, *, session_id: str) -> str:
        """Legacy completed WebM path, retained for compatibility only."""
        if not audio or len(audio) > 20_000_000:
            raise ValueError("Invalid audio")
        import av
        with av.open(io.BytesIO(audio), "r") as container:
            frames = []
            resampler = av.AudioResampler(format="fltp", layout="mono", rate=16000)
            for frame in container.decode(audio=0):
                frames.extend(resampler.resample(frame))
            frames.extend(resampler.resample(None))
            if not frames:
                return ""
            arr = np.concatenate([x.to_ndarray().reshape(-1) for x in frames]).astype("<f4")
        result = await self.consume_pcm(b"", session_id=session_id, end=True) if not arr.size else None
        if result is not None:
            return str(result["transcript"])
        for offset in range(0, arr.size, 1600):
            result = await self.consume_pcm(arr[offset:offset + 1600].tobytes(),
                                            session_id=session_id, end=False)
        last = await self.consume_pcm(b"", session_id=session_id, end=True)
        return str(last["transcript"])
