"""Fail-closed sherpa-onnx KWS/streaming-ASR adapter.

Models are intentionally provisioned by the local owner.  This keeps model
licensing, storage location, and microphone activation outside the package.
"""
from __future__ import annotations

import asyncio
import importlib.util
import io
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SherpaOnnxConfig:
    enabled: bool
    tokens_path: Path | None
    encoder_path: Path | None
    decoder_path: Path | None
    joiner_path: Path | None
    keywords_path: Path | None
    license_accepted: bool

    @classmethod
    def from_env(cls) -> "SherpaOnnxConfig":
        def path(name: str) -> Path | None:
            value = os.getenv(name, "").strip()
            return Path(value).expanduser() if value else None
        return cls(
            enabled=os.getenv("AURA_NIRVANA_VOICE_ENABLED", "0").strip().casefold() in {"1", "true", "yes", "on"},
            tokens_path=path("AURA_SHERPA_TOKENS_PATH"),
            encoder_path=path("AURA_SHERPA_ENCODER_PATH"),
            decoder_path=path("AURA_SHERPA_DECODER_PATH"),
            joiner_path=path("AURA_SHERPA_JOINER_PATH"),
            keywords_path=path("AURA_SHERPA_KEYWORDS_PATH"),
            license_accepted=os.getenv("AURA_SHERPA_MODEL_LICENSE_ACCEPTED", "0").strip() == "1",
        )

    def health(self) -> dict[str, object]:
        required = {
            "tokens": self.tokens_path, "encoder": self.encoder_path,
            "decoder": self.decoder_path, "joiner": self.joiner_path,
            "keywords": self.keywords_path,
        }
        missing = [name for name, value in required.items() if value is None or not value.is_file()]
        installed = importlib.util.find_spec("sherpa_onnx") is not None
        ready = self.enabled and installed and self.license_accepted and not missing
        if not self.enabled:
            reason = "disabled_by_feature_flag"
        elif not installed:
            reason = "python_package_unavailable"
        elif not self.license_accepted:
            reason = "model_license_not_acknowledged"
        elif missing:
            reason = "model_files_unavailable"
        else:
            reason = "ready"
        return {"provider": "sherpa-onnx", "enabled": self.enabled, "available": ready,
                "reason": reason, "missing": missing, "license_acknowledged": self.license_accepted}


class SherpaOnnxRecognizer:
    """Local streaming-ASR configuration boundary.

    Uses sherpa-onnx's transducer streaming API with locally provisioned ONNX
    files.  Incoming WebM/WAV is decoded locally to 16 kHz mono; no audio is
    written to disk.  A configured keywords file is also required as a guard
    against accidentally enabling ASR without the corresponding KWS asset.
    """

    def __init__(self, config: SherpaOnnxConfig) -> None:
        health = config.health()
        if not health["available"]:
            raise RuntimeError(f"sherpa-onnx is not ready: {health['reason']}")
        self._config = config
        self._recognizer = None
        self._keyword_spotter = None
        self._lock = asyncio.Lock()

    def _create_recognizer(self):
        import sherpa_onnx
        return sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=str(self._config.tokens_path), encoder=str(self._config.encoder_path),
            decoder=str(self._config.decoder_path), joiner=str(self._config.joiner_path),
            num_threads=1, sample_rate=16000, feature_dim=80,
            decoding_method="greedy_search", provider="cpu",
        )

    def _create_keyword_spotter(self):
        import sherpa_onnx
        return sherpa_onnx.KeywordSpotter(
            tokens=str(self._config.tokens_path), encoder=str(self._config.encoder_path),
            decoder=str(self._config.decoder_path), joiner=str(self._config.joiner_path),
            keywords_file=str(self._config.keywords_path), num_threads=1,
            sample_rate=16000, feature_dim=80, decoding_method="greedy_search",
            provider="cpu",
        )

    @staticmethod
    def _decode_16khz_mono(audio: bytes):
        import av
        import numpy as np
        with av.open(io.BytesIO(audio), mode="r") as container:
            stream = next((item for item in container.streams if item.type == "audio"), None)
            if stream is None:
                raise ValueError("Audio payload contains no audio stream")
            resampler = av.AudioResampler(format="fltp", layout="mono", rate=16000)
            frames = []
            for frame in container.decode(audio=stream.index):
                frames.extend(resampler.resample(frame))
            frames.extend(resampler.resample(None))
        samples = np.concatenate([frame.to_ndarray().reshape(-1) for frame in frames]).astype(np.float32, copy=False) if frames else None
        if samples is None or samples.size == 0:
            raise ValueError("Audio payload contains no decodable samples")
        return samples

    async def transcribe(self, audio: bytes, *, session_id: str) -> str:
        if not audio or len(audio) > 20_000_000:
            raise ValueError("Audio payload is empty or exceeds the 20 MB limit")
        async with self._lock:
            if self._recognizer is None:
                self._recognizer = await asyncio.to_thread(self._create_recognizer)
            if self._keyword_spotter is None:
                self._keyword_spotter = await asyncio.to_thread(self._create_keyword_spotter)
            samples = await asyncio.to_thread(self._decode_16khz_mono, audio)
            def decode() -> str:
                keyword_stream = self._keyword_spotter.create_stream()
                keyword_stream.accept_waveform(16000, samples)
                while self._keyword_spotter.is_ready(keyword_stream):
                    self._keyword_spotter.decode_stream(keyword_stream)
                if not str(self._keyword_spotter.get_result(keyword_stream).keyword).strip():
                    return ""
                stream = self._recognizer.create_stream()
                stream.accept_waveform(16000, samples)
                while self._recognizer.is_ready(stream):
                    self._recognizer.decode_stream(stream)
                return str(self._recognizer.get_result(stream).text).strip()
            return (await asyncio.to_thread(decode))[:8000]
