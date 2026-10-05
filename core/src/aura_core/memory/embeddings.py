from __future__ import annotations

from typing import Any, Protocol

import httpx

from .models import Embedding


class EmbeddingProvider(Protocol):
    model: str

    async def embed(
        self,
        texts: list[str],
    ) -> list[Embedding]:
        ...


class OllamaEmbeddingProvider:
    def __init__(
        self,
        model: str = "bge-m3",
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def embed(
        self,
        texts: list[str],
    ) -> list[Embedding]:
        if not texts:
            return []

        async with httpx.AsyncClient(
            timeout=self.timeout
        ) as client:
            response = await client.post(
                f"{self.base_url}/api/embed",
                json={
                    "model": self.model,
                    "input": texts,
                },
            )

            response.raise_for_status()

            payload: dict[str, Any] = response.json()

        vectors = payload.get("embeddings")

        if not isinstance(vectors, list):
            raise RuntimeError(
                "Ollama embedding response has no embeddings list"
            )

        if len(vectors) != len(texts):
            raise RuntimeError(
                "Embedding count mismatch: "
                f"expected={len(texts)} "
                f"actual={len(vectors)}"
            )

        result: list[Embedding] = []

        for vector in vectors:
            if not isinstance(vector, list) or not vector:
                raise RuntimeError(
                    "Invalid embedding vector"
                )

            values = [
                float(value)
                for value in vector
            ]

            result.append(
                Embedding(
                    vector=values,
                    model=self.model,
                    dimensions=len(values),
                )
            )

        return result

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(
                timeout=10.0
            ) as client:
                response = await client.get(
                    f"{self.base_url}/api/tags"
                )

                response.raise_for_status()

            return True

        except Exception:
            return False
