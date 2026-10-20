from fastapi.testclient import TestClient

from aura_core.application.api import create_api
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig


def _client():
    config = RuntimeConfig(
        runtime="ollama",
        model="qwen3:4b-instruct-2507-q4_K_M",
        temperature=0.7,
        max_tokens=32,
    )
    return TestClient(create_api(
        config,
        backend_config=BackendConfig(endpoint="http://127.0.0.1:11434", timeout=30.0),
    ))


def test_proactive_suggestions_api_starts_empty_and_is_read_only():
    response = _client().get("/api/proactive/suggestions")
    assert response.status_code == 200
    assert response.json() == {"suggestions": []}


def test_capability_proposals_api_starts_empty():
    response = _client().get("/api/capabilities/proposals")
    assert response.status_code == 200
    assert response.json() == {"proposals": []}


def test_discovery_requires_live_kernel_registries():
    response = _client().post(
        "/api/capabilities/discover/research",
        json={"category": "research"},
    )
    assert response.status_code == 503
