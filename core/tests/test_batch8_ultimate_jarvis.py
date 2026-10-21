from __future__ import annotations

from fastapi.testclient import TestClient

from aura_core.application.api import create_api
from aura_core.application.episodic_memory import EpisodicMemoryStore
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig


class StubTransport:
    def post_json(self, endpoint: str, payload: dict, timeout: float) -> dict:
        return {
            "model": "qwen3-test",
            "message": {"role": "assistant", "content": "Kanıtları birleştiren yanıt."},
            "done": True,
        }

    def get_json(self, endpoint: str, timeout: float) -> dict:
        return {"models": []}


def make_client() -> TestClient:
    app = create_api(
        RuntimeConfig(runtime="ollama", model="qwen3-test", temperature=0.2, max_tokens=64),
        backend_config=BackendConfig(endpoint="http://127.0.0.1:11434", timeout=2.0),
        transport=StubTransport(),
    )
    return TestClient(app)


def test_semantic_recall_ranks_shared_concepts_and_isolates_principals(tmp_path) -> None:
    store = EpisodicMemoryStore(tmp_path / "semantic.sqlite3")
    store.remember(
        principal_id="alice",
        kind="preference",
        content="Kullanıcı kısa Türkçe yanıtları tercih ediyor.",
        tags=("language", "response-style"),
        importance=5,
    )
    store.remember(
        principal_id="alice",
        kind="reasoning",
        content="Hava sıcaklığı ile sistem CPU yükünü birlikte değerlendirmek gerekir.",
        tags=("weather", "telemetry"),
        importance=4,
    )
    store.remember(
        principal_id="bob",
        kind="preference",
        content="Prefer long English answers about weather.",
        tags=("weather",),
        importance=5,
    )

    related = store.recall_related(principal_id="alice", query="hava durumu ve CPU yükü", limit=5)
    assert related
    assert related[0]["kind"] == "reasoning"
    assert "relevance_score" in related[0]
    assert all(item["principal_id"] == "alice" for item in related)
    assert store.recall_related(principal_id="bob", query="CPU yükü") == []


def test_jarvis_related_memory_endpoint_returns_ranked_context(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AURA_MEMORY_DB", str(tmp_path / "api.sqlite3"))
    with make_client() as client:
        created = client.post("/api/jarvis/memory", json={
            "principal_id": "local-user",
            "kind": "preference",
            "content": "Yanıtları Türkçe ve kısa tut.",
            "tags": ["language", "concise"],
            "importance": 5,
        })
        assert created.status_code == 200
        response = client.get("/api/jarvis/memory/related", params={
            "principal_id": "local-user",
            "query": "Türkçe kısa yanıt",
        })
        assert response.status_code == 200
        assert response.json()["count"] == 1
        assert response.json()["items"][0]["kind"] == "preference"


def test_cross_capability_endpoint_synthesizes_multi_provider_evidence() -> None:
    with make_client() as client:
        response = client.post("/api/reasoning/cross-capability", json={
            "objective": "Sistem yükünü ve hava koşullarını birlikte değerlendir.",
            "evidence": [
                {"capability_id": "weather.read", "provider_id": "weather-provider", "result": {"temperature_c": 31}},
                {"capability_id": "system.telemetry", "provider_id": "local-telemetry", "result": {"cpu_percent": 94}},
            ],
        })
        assert response.status_code == 200
        body = response.json()
        assert body["evidence_count"] == 2
        assert body["distinct_providers"] == 2
        assert body["tool_execution_performed"] is False
        assert body["synthesis"] == "Kanıtları birleştiren yanıt."


def test_fastapi_lifespan_starts_and_stops_telemetry_daemon(monkeypatch) -> None:
    monkeypatch.setenv("AURA_TELEMETRY_DAEMON_ENABLED", "1")
    app = make_client().app
    calls: list[str] = []

    def start() -> None:
        calls.append("start")

    async def stop() -> None:
        calls.append("stop")

    app.state.telemetry_daemon.start = start
    app.state.telemetry_daemon.stop = stop

    with TestClient(app):
        assert calls == ["start"]
    assert calls == ["start", "stop"]
