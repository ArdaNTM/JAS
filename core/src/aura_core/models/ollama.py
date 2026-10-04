from __future__ import annotations

from typing import Any

import httpx


class OllamaProvider:
    provider_id = "llm:ollama"

    def __init__(
        self,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def generate(
        self,
        prompt: str,
        options: dict[str, object] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }

        if options:
            payload["options"] = dict(options)

        async with httpx.AsyncClient(
            timeout=self.timeout
        ) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json=payload,
            )

        response.raise_for_status()

        data = response.json()

        content = data.get("response")

        if not isinstance(content, str):
            raise RuntimeError(
                "Ollama returned an invalid response"
            )

        return content