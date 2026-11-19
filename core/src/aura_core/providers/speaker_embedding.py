"""Offline speaker embeddings from a pre-provisioned local SpeechBrain model."""
from __future__ import annotations
import io
import math
from pathlib import Path
from typing import Protocol, Sequence


class SpeakerEmbeddingProvider(Protocol):
    def embed(self, wav_bytes: bytes) -> Sequence[float]: ...


class SpeechBrainLocalEmbeddingProvider:
    """ECAPA-style embeddings; local model only, no implicit model download."""
    def __init__(self, model_dir: str | Path) -> None:
        directory = Path(model_dir).expanduser().resolve(strict=True)
        if not directory.is_dir() or not (directory / "hyperparams.yaml").is_file():
            raise ValueError("A pre-provisioned local SpeechBrain model directory is required")
        try:
            import soundfile as sf
            import torch
            from speechbrain.inference.speaker import EncoderClassifier
        except ImportError as exc:
            raise RuntimeError("Install optional local speaker stack: speechbrain, torch and soundfile") from exc
        self._sf, self._torch = sf, torch
        self._model = EncoderClassifier.from_hparams(
            source=str(directory), savedir=str(directory), run_opts={"device": "cpu"}
        )

    def embed(self, wav_bytes: bytes) -> Sequence[float]:
        if not isinstance(wav_bytes, bytes) or not 44 <= len(wav_bytes) <= 2_000_000:
            raise ValueError("WAV payload must contain 44 bytes..2 MB")
        try:
            samples, rate = self._sf.read(io.BytesIO(wav_bytes), dtype="float32", always_2d=True)
        except Exception as exc:
            raise ValueError("Invalid WAV payload") from exc
        if rate != 16_000:
            raise ValueError("Speaker recognition requires 16 kHz audio")
        if not 16_000 <= samples.shape[0] <= 160_000:
            raise ValueError("Audio duration must be 1..10 seconds")
        mono = samples.mean(axis=1)
        if not all(math.isfinite(float(x)) for x in mono):
            raise ValueError("Audio contains non-finite samples")
        with self._torch.inference_mode():
            result = self._model.encode_batch(self._torch.from_numpy(mono).unsqueeze(0))
        vector = result.detach().cpu().numpy().reshape(-1).tolist()
        if not vector or len(vector) > 8192:
            raise ValueError("Speaker model returned an invalid embedding")
        norm = math.sqrt(sum(float(x) ** 2 for x in vector))
        if not math.isfinite(norm) or norm <= 1e-12:
            raise ValueError("Speaker model returned a zero or invalid embedding")
        return tuple(float(x) / norm for x in vector)
