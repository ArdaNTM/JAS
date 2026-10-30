"""Finite local inference retry and Ollama warmup tests."""
from __future__ import annotations

import io
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from aura_core.runtime.errors import BackendUnavailableError
from aura_core.runtime.transport import HttpJsonTransport


ENDPOINT = "http://127.0.0.1:11434/api/chat"
PAYLOAD = {"model": "qwen3:latest", "messages": [{"role": "user", "content": "test"}], "stream": False}


def ok_response():
    return httpx.Response(
        200,
        request=httpx.Request("POST", ENDPOINT),
        json={"message": {"content": "OK"}, "done": True},
    )


def test_transient_connection_failure_is_retried_once():
    response = ok_response()
    with patch("aura_core.runtime.transport.httpx.post",
               side_effect=[httpx.ConnectError("connection reset"), response]) as post, \
         patch("aura_core.runtime.transport.sleep") as wait:
        assert HttpJsonTransport().post_json(ENDPOINT, PAYLOAD, 30)["done"] is True
    assert post.call_count == 2
    wait.assert_called_once()


def test_two_connect_failures_return_retryable_backend_error_without_secret_leak():
    with patch("aura_core.runtime.transport.httpx.post",
               side_effect=httpx.ConnectError("user:secret@127.0.0.1")) as post, \
         patch("aura_core.runtime.transport.sleep"):
        with pytest.raises(BackendUnavailableError) as exc:
            HttpJsonTransport().post_json(ENDPOINT, PAYLOAD, 30)
    assert post.call_count == 2
    assert "secret" not in str(exc.value)


def test_read_timeout_does_not_replay_model_generation():
    with patch("aura_core.runtime.transport.httpx.post",
               side_effect=httpx.ReadTimeout("private prompt")) as post:
        with pytest.raises(BackendUnavailableError, match="model response timed out"):
            HttpJsonTransport().post_json(ENDPOINT, PAYLOAD, 30)
    post.assert_called_once()


def test_upstream_http_errors_are_not_replayed():
    response = httpx.Response(500, request=httpx.Request("POST", ENDPOINT))
    with patch("aura_core.runtime.transport.httpx.post", return_value=response) as post:
        with pytest.raises(httpx.HTTPStatusError):
            HttpJsonTransport().post_json(ENDPOINT, PAYLOAD, 30)
    post.assert_called_once()


def preflight_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "preflight_ollama.py"
    spec = importlib.util.spec_from_file_location("test_ollama_preflight", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preflight_checks_installed_model_and_completes_chat(monkeypatch):
    script = preflight_module()
    monkeypatch.setenv("AURA_RUNTIME", "ollama")
    monkeypatch.setenv("AURA_MODEL", "qwen3:latest")
    monkeypatch.setenv("AURA_BACKEND_ENDPOINT", "http://127.0.0.1:11434")
    seen = []

    def fake_urlopen(request, timeout):
        seen.append((request.full_url, request.data, timeout))
        if request.full_url.endswith("/api/tags"):
            return io.BytesIO(json.dumps({"models": [{"name": "qwen3:latest"}]}).encode())
        return io.BytesIO(json.dumps({"message": {"content": "ready"}, "done": True}).encode())

    monkeypatch.setattr(script, "urlopen", fake_urlopen)
    assert "chat inference completed" in script.preflight()
    assert [x[0].split("/")[-1] for x in seen] == ["tags", "chat"]
    payload = json.loads(seen[1][1])
    assert payload["model"] == "qwen3:latest"
    assert payload["stream"] is False
    assert payload["keep_alive"] == "10m"


def test_preflight_fails_without_exact_installed_model(monkeypatch):
    script = preflight_module()
    monkeypatch.setenv("AURA_RUNTIME", "ollama")
    monkeypatch.setenv("AURA_MODEL", "qwen3:missing")
    monkeypatch.setenv("AURA_BACKEND_ENDPOINT", "http://127.0.0.1:11434")
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        return io.BytesIO(json.dumps({"models": [{"name": "qwen3:latest"}]}).encode())

    monkeypatch.setattr(script, "urlopen", fake_urlopen)
    with pytest.raises(ValueError, match="not installed"):
        script.preflight()
    assert len(calls) == 1


def test_nonlocal_ollama_preflight_is_rejected_before_network(monkeypatch):
    script = preflight_module()
    monkeypatch.setenv("AURA_RUNTIME", "ollama")
    monkeypatch.setenv("AURA_MODEL", "qwen3:latest")
    monkeypatch.setenv("AURA_BACKEND_ENDPOINT", "http://evil.example:11434")
    def invalid_call(*args, **kwargs):
        raise AssertionError("Network should not be called")
    monkeypatch.setattr(script, "urlopen", invalid_call)
    with pytest.raises(ValueError, match="loopback"):
        script.preflight()


def test_non_ollama_runtime_does_not_assume_ollama(monkeypatch):
    script = preflight_module()
    monkeypatch.setenv("AURA_RUNTIME", "mock")
    assert "Skipped" in script.preflight()
