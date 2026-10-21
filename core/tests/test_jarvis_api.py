from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from aura_core.application.jarvis_api import router


def test_memory_api_persists_and_requires_principal_scope(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AURA_MEMORY_DB", str(tmp_path / "api-memory.sqlite3"))
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    created = client.post(
        "/api/jarvis/memory",
        json={
            "principal_id": "local-user",
            "kind": "lesson",
            "content": "Check the evidence before responding.",
            "tags": ["quality"],
            "importance": 4,
        },
    )
    assert created.status_code == 200
    memory_id = created.json()["memory_id"]

    own = client.get("/api/jarvis/memory", params={"principal_id": "local-user"})
    other = client.get("/api/jarvis/memory", params={"principal_id": "other-user"})
    assert own.status_code == 200 and own.json()["count"] == 1
    assert other.status_code == 200 and other.json()["count"] == 0

    deleted = client.delete(
        f"/api/jarvis/memory/{memory_id}",
        params={"principal_id": "local-user"},
    )
    assert deleted.status_code == 200


def test_adaptation_api_requires_confirmation_and_allowlisted_strategy() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    created = client.post(
        "/api/jarvis/adaptations/proposals",
        json={
            "strategy_id": "retry_transient_transport_once",
            "rationale": "Bounded retries can recover transient timeouts.",
        },
    )
    assert created.status_code == 200
    proposal_id = created.json()["proposal_id"]

    rejected = client.post(
        f"/api/jarvis/adaptations/proposals/{proposal_id}/approve",
        json={"confirmed": False},
    )
    assert rejected.status_code == 409

    approved = client.post(
        f"/api/jarvis/adaptations/proposals/{proposal_id}/approve",
        json={"confirmed": True},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    unknown = client.post(
        "/api/jarvis/adaptations/proposals",
        json={"strategy_id": "run_untrusted_code", "rationale": "unsafe"},
    )
    assert unknown.status_code == 422


def test_initiative_api_only_accepts_allowlisted_events() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    result = client.post(
        "/api/jarvis/initiatives/observe",
        json={
            "event_type": "TaskFailed",
            "correlation_id": "task-42",
            "payload": {"task_id": "task-42"},
        },
    )
    assert result.status_code == 200
    assert result.json()["can_execute"] is False

    unsupported = client.post(
        "/api/jarvis/initiatives/observe",
        json={"event_type": "RunArbitraryAction"},
    )
    assert unsupported.status_code == 422
