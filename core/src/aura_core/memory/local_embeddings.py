"""Optional offline sentence-transformers embeddings.

The model is loaded only from a local path; this module never downloads models
or contacts a hosted inference service.
"""
from __future__ import annotations

import asyncio
import math
from pathlib import Path
from typing import Protocol


class VectorEmbedder(Protocol):
    model: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class LocalSentenceTransformerEmbedder:
    def __init__(self, model_path: str, *, device: str = "cpu") -> None:
        path = Path(model_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(
                "Local embedding model path does not exist; install/download the model manually first."
            )
        self.model_path = str(path)
        self.model = path.name
        self.device = device
        self._model = None

    def _load_and_encode(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "Install the optional 'local-embeddings' dependency group to enable sentence-transformers."
                ) from exc
            self._model = SentenceTransformer(
                self.model_path,
                device=self.device,
                local_files_only=True,
            )
        vectors = self._model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True,
            show_progress_bar=False,
        )
        result = [[float(value) for value in vector] for vector in vectors]
        if any(not vector or any(not math.isfinite(value) for value in vector) for vector in result):
            raise ValueError("Embedding model returned an invalid vector")
        return result

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if len(texts) > 128:
            raise ValueError("At most 128 texts can be embedded per batch")
        if any(not isinstance(text, str) or len(text) > 12000 for text in texts):
            raise ValueError("Each embedding input must be text of at most 12000 characters")
        if not texts:
            return []
        return await asyncio.to_thread(self._load_and_encode, texts)
