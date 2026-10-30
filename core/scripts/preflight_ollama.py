"""Windows launcher preflight for a *local* Ollama inference model.

Unlike /api/tags readiness this performs one bounded /api/chat request,
so the model is loaded before the browser attempts a researched response.
The prompt contains no user data or research evidence.
"""
from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def preflight() -> str:
    runtime = os.getenv("AURA_RUNTIME", "ollama").strip().casefold()
    if runtime != "ollama":
        return "Skipped local Ollama preflight: non-Ollama runtime"

    base = os.getenv("AURA_BACKEND_ENDPOINT", "http://127.0.0.1:11434").strip().rstrip("/")
    parsed = urlsplit(base)
    if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("Local Ollama preflight requires a loopback HTTP endpoint")
    model = os.getenv("AURA_MODEL", "").strip()
    if not model:
        raise ValueError("AURA_MODEL is required")
    timeout = min(max(float(os.getenv("AURA_OLLAMA_PREFLIGHT_TIMEOUT", "180")), 10), 600)

    def request(path: str, payload: dict | None, wait: float) -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = Request(
            base + path,
            data=data,
            headers={"Content-Type": "application/json"} if data else {},
            method="POST" if data is not None else "GET",
        )
        with urlopen(req, timeout=wait) as response:
            decoded = json.load(response)
        if not isinstance(decoded, dict):
            raise ValueError("Ollama returned a non-object JSON response")
        return decoded

    tags = request("/api/tags", None, min(timeout, 15))
    available = {item["name"] for item in tags.get("models", [])
                 if isinstance(item, dict) and isinstance(item.get("name"), str)}
    if model not in available:
        raise ValueError("Configured AURA_MODEL is not installed in local Ollama")

    completion = request("/api/chat", {
        "model": model,
        "stream": False,
        "keep_alive": "10m",
        "messages": [{"role": "user", "content": "Say ready."}],
        "options": {"num_predict": 96, "temperature": 0.0},
    }, timeout)
    if completion.get("done") is not True or not isinstance(completion.get("message"), dict):
        raise ValueError("Ollama model warmup did not finish a valid chat response")
    return f"Local Ollama ready: model={model} (chat inference completed)"


def main() -> int:
    try:
        print(preflight())
        return 0
    except (HTTPError, URLError, OSError, ValueError, TypeError, KeyError, TimeoutError) as exc:
        # Do not leak host credentials, arbitrary backend response payloads or prompts.
        if isinstance(exc, HTTPError):
            kind = f"HTTP {exc.code}"
        else:
            kind = type(exc).__name__
        print(
            f"AURA Ollama preflight failed ({kind}). "
            "Check Ollama server, installed AURA_MODEL, GPU memory and "
            "AURA_OLLAMA_PREFLIGHT_TIMEOUT.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
