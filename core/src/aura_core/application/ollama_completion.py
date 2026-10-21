"""Ollama-compatible JSON completion adapter; inference is not an authorization boundary."""
from __future__ import annotations

import json
from typing import Any, Mapping

import httpx


class OllamaJSONCompletionProvider:
    """Provider adapter for Ollama's chat endpoint, injectable like any inference backend."""

    def __init__(
        self, *, base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen3", timeout_seconds: float = 30.0,
    ) -> None:
        if not base_url.startswith(("http://127.0.0.1", "http://localhost", "https://")):
            raise ValueError("Ollama endpoint must be loopback HTTP or HTTPS")
        if not model.strip() or timeout_seconds <= 0:
            raise ValueError("model and positive timeout are required")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds

    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> Mapping[str, Any]:
        timeout = httpx.Timeout(self._timeout)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "stream": False,
                    "format": "json",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
        content = payload.get("message", {}).get("content")
        if not isinstance(content, str) or len(content) > 32_000:
            raise ValueError("Inference provider returned missing or oversized JSON content")
        decoded = json.loads(content)
        if not isinstance(decoded, dict):
            raise ValueError("Inference provider must return a JSON object")
        return decoded
