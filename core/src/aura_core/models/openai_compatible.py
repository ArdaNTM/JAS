from __future__ import annotations

import os
from typing import Any

import httpx


class OpenAICompatibleProvider:
    def __init__(
        self,
        provider_id: str,
        base_url: str,
        model: str,
        api_key_env: str,
        timeout: float = 120.0,
    ) -> None:
        self.provider_id = provider_id
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key_env = api_key_env
        self.timeout = timeout

    async def generate(
        self,
        prompt: str,
        options: dict[str, object] | None = None,
    ) -> str:
        api_key = os.getenv(self.api_key_env)

        if not api_key:
            raise RuntimeError(
                f"Missing environment variable: {self.api_key_env}"
            )

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        }

        if options:
            payload.update(options)

        async with httpx.AsyncClient(
            timeout=self.timeout
        ) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        response.raise_for_status()

        data = response.json()

        choices = data.get("choices")

        if not isinstance(choices, list) or not choices:
            raise RuntimeError(
                "OpenAI-compatible provider returned no choices"
            )

        message = choices[0].get("message")

        if not isinstance(message, dict):
            raise RuntimeError(
                "OpenAI-compatible provider returned invalid message"
            )

        content = message.get("content")

        if not isinstance(content, str):
            raise RuntimeError(
                "OpenAI-compatible provider returned invalid content"
            )

        return content