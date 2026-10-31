"""Streaming Ollama token safety and Turkish TTS normalization regressions."""
from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from aura_core.application.api import create_api
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig
from aura_core.contracts.messages import InferenceRequest
from aura_core.runtime.adapter import AdapterBackend
from aura_core.runtime.transport import HttpJsonTransport


def speech_cleaner():
    folder = Path(__file__).resolve().parents[1] / "scripts"
    spec = importlib.util.spec_from_file_location("aura_test_tts_text", folder / "tts_text.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.clean_for_speech


def test_speech_cleaner_strips_markdown_links_and_urls_without_losing_turkish():
    clean = speech_cleaner()
    sample = (
        "# **Kaynaklar**\n"
        "1. **Birinci gelişme:** Türkçe *özet*. [Kaynak](https://example.org/doc)\n"
        "2. İkinci gelişme: www.example.com\n"
        "```python\nprint('not spoken')\n```\n"
        "3. **Üçüncü gelişme:** Tamamlandı. [1]"
    )
    result = clean(sample)
    assert "yıldız" not in result.lower()
    assert "Birinci gelişme" in result
    assert "İkinci gelişme" in result
    assert "Üçüncü gelişme" in result
    assert "**" not in result and "https:" not in result
    assert "print" not in result


def test_transport_parses_genuine_ollama_ndjson_without_aggregating():
    class DummyResponse:
        def raise_for_status(self):
            pass
        def iter_lines(self):
            yield json.dumps({"message": {"content": "Merhaba "}, "done": False})
            yield json.dumps({"message": {"content": "AURA"}, "done": False})
            yield json.dumps({"done": True, "done_reason": "stop"})
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    class DummyClient:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def stream(self, method, endpoint, json):
            assert method == "POST"
            assert json["stream"] is True
            return DummyResponse()
    with patch("aura_core.runtime.transport.httpx.Client", DummyClient):
        events = list(HttpJsonTransport().post_stream_json(
            "http://127.0.0.1:11434/api/chat", {"stream": True}, 30
        ))
    assert len(events) == 3
    assert events[-1]["done"] is True


def test_runtime_stream_keeps_chunks_separate_and_no_thoughts(monkeypatch):
    monkeypatch.setenv("AURA_OLLAMA_FAST_RESPONSE", "1")
    class Transport:
        def post_stream_json(self, endpoint, payload, timeout):
            assert payload["stream"] is True
            assert payload["think"] is False
            yield {"message": {"content": "Birinci. ", "thinking": "private"}, "done": False}
            yield {"message": {"content": "İkinci. Üçüncü."}, "done": False}
            yield {"done": True, "done_reason": "stop"}
    backend = AdapterBackend(BackendConfig(), Transport())
    events = list(backend.infer_stream(InferenceRequest(
        model="qwen3:latest", messages=[{"role": "user", "content": "Üç gelişme"}]
    )))
    assert [e["delta"] for e in events if "delta" in e] == [
        "Birinci. ", "İkinci. Üçüncü.",
    ]
    assert events[-1] == {"done": True, "finish_reason": "stop"}
    assert all("thinking" not in event for event in events)


def test_stream_endpoint_requires_auth_and_delivers_all_three_events():
    class Transport:
        def post_json(self, *args, **kwargs):
            return {"message": {"content": "fallback"}, "done": True}
        def get_json(self, *args, **kwargs):
            return {"models": []}
        def post_stream_json(self, endpoint, payload, timeout):
            yield {"message": {"content": "Birinci. "}, "done": False}
            yield {"message": {"content": "İkinci. "}, "done": False}
            yield {"message": {"content": "Üçüncü."}, "done": False}
            yield {"done": True, "done_reason": "stop"}
    app = create_api(
        RuntimeConfig(runtime="ollama", model="test", max_tokens=None),
        backend_config=BackendConfig(endpoint="http://127.0.0.1:11434"),
        transport=Transport(),
    )
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "local_owner"
    unauthorized = TestClient(app).post(
        "/api/assistant/respond/stream", json={"message": "Üç gelişmeyi anlat"}
    )
    assert unauthorized.status_code == 401
    response = TestClient(app).post(
        "/api/assistant/respond/stream",
        json={"message": "Üç gelişmeyi anlat"},
        headers={"Authorization": "Bearer " + "t" * 40},
    )
    assert response.status_code == 200, response.text
    chunks = [json.loads(line) for line in response.text.splitlines()]
    assert "".join(c["delta"] for c in chunks if "delta" in c) == "Birinci. İkinci. Üçüncü."
    assert chunks[-1]["done"] is True
