"""Opt-in interactive Ollama latency profile without changing inference authority."""
from __future__ import annotations

from aura_core.config.backend import BackendConfig
from aura_core.contracts.messages import InferenceRequest
from aura_core.runtime.adapter import AdapterBackend


class FakeTransport:
    def __init__(self):
        self.payload = None

    def post_json(self, endpoint, payload, timeout):
        self.payload = payload
        return {"message": {"content": "Merhaba"}, "done": True}


def test_interactive_mode_bounds_generation_and_disables_optional_thinking(monkeypatch):
    monkeypatch.setenv("AURA_OLLAMA_FAST_RESPONSE", "1")
    monkeypatch.setenv("AURA_OLLAMA_FAST_MAX_TOKENS", "384")
    transport = FakeTransport()
    backend = AdapterBackend(BackendConfig(), transport)
    result = backend.infer(InferenceRequest(
        model="qwen3:latest", messages=[{"role": "user", "content": "Merhaba"}],
    ))
    assert result.content == "Merhaba"
    assert transport.payload["think"] is False
    assert transport.payload["keep_alive"] == "10m"
    assert transport.payload["options"]["num_predict"] == 384


def test_explicit_token_budget_wins_and_fast_mode_can_be_disabled(monkeypatch):
    monkeypatch.setenv("AURA_OLLAMA_FAST_RESPONSE", "1")
    transport = FakeTransport()
    backend = AdapterBackend(BackendConfig(), transport)
    backend.infer(InferenceRequest(
        model="qwen3:latest", messages=[{"role": "user", "content": "test"}], max_tokens=512,
    ))
    assert transport.payload["options"]["num_predict"] == 512

    monkeypatch.setenv("AURA_OLLAMA_FAST_RESPONSE", "0")
    backend.infer(InferenceRequest(
        model="qwen3:latest", messages=[{"role": "user", "content": "test"}],
    ))
    assert "think" not in transport.payload
    assert "keep_alive" not in transport.payload
    assert "num_predict" not in transport.payload["options"]


def test_interactive_budget_is_bounded(monkeypatch):
    monkeypatch.setenv("AURA_OLLAMA_FAST_RESPONSE", "1")
    monkeypatch.setenv("AURA_OLLAMA_FAST_MAX_TOKENS", "50000")
    transport = FakeTransport()
    AdapterBackend(BackendConfig(), transport).infer(InferenceRequest(
        model="qwen3:latest", messages=[{"role": "user", "content": "test"}]
    ))
    assert transport.payload["options"]["num_predict"] == 2048
