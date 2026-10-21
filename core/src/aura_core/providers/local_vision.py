"""Local-only Ollama vision provider (Qwen-VL/LLaVA compatible)."""
from __future__ import annotations

import base64
import ipaddress
from urllib.parse import urlparse

import httpx


def _validate_local_endpoint(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme != "http" or not parsed.hostname:
        raise ValueError("vision endpoint must be an explicit local HTTP URL")
    host = parsed.hostname.casefold()
    allowed = host in {"localhost"} 
    try:
        allowed = allowed or ipaddress.ip_address(host).is_loopback
    except ValueError:
        pass
    if not allowed:
        raise ValueError("cloud and non-loopback vision endpoints are forbidden")
    if parsed.username or parsed.password:
        raise ValueError("credentials in endpoint URLs are forbidden")
    return base_url.rstrip("/")


class LocalOllamaVisionProvider:
    def __init__(self, *, model: str = "qwen2.5vl:3b", base_url: str = "http://127.0.0.1:11434", timeout: float = 60.0) -> None:
        if not 1 <= timeout <= 180:
            raise ValueError("timeout must be between 1 and 180 seconds")
        self.model = model
        self.base_url = _validate_local_endpoint(base_url)
        self.timeout = timeout

    async def analyze(self, *, image_bytes: bytes, prompt: str) -> str:
        if not image_bytes or len(image_bytes) > 8 * 1024 * 1024:
            raise ValueError("image must be between 1 byte and 8 MiB")
        prompt = prompt.strip()
        if not prompt or len(prompt) > 4000:
            raise ValueError("prompt must contain 1..4000 characters")
        encoded = base64.b64encode(image_bytes).decode("ascii")
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await client.post(
                self.base_url + "/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "messages": [{"role": "user", "content": prompt, "images": [encoded]}],
                    "options": {"temperature": 0},
                },
            )
            response.raise_for_status()
            payload = response.json()
        content = payload.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("local vision provider returned no message content")
        return content.strip()
