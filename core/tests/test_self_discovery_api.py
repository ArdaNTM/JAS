"""Authenticated discovery API is read-only and owner-scoped."""
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from aura_core.evolution.self_discovery_api import router


class FakeEngine:
    principal_id = "local_owner"

    def status(self):
        return {"count": 1, "next_allowed": 1000,
                "mode": "read_only_owner_review", "authorization_granted": False,
                "execution_performed": False}

    def proposals(self, limit):
        return [{"id": "candidate", "full_name": "org/repo",
                 "url": "https://github.com/org/repo", "license_id": "MIT",
                 "summary": "Offline", "capability": "MCP",
                 "status": "awaiting_owner_review"}]

    async def run_once(self):
        return {**self.status(), "items": self.proposals(10),
                "added": 0, "note": "cooldown"}


def test_discovery_endpoints_require_authenticated_owner():
    app = FastAPI()
    app.include_router(router)
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = "local_owner"
    app.state.self_discovery_engine = FakeEngine()
    client = TestClient(app)
    assert client.get("/api/evolution/discovery/proposals").status_code == 401
    headers = {"Authorization": "Bearer " + "t" * 40}
    listing = client.get("/api/evolution/discovery/proposals", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    result = client.post("/api/evolution/discovery/run", headers=headers)
    assert result.status_code == 200
    assert result.json()["execution_performed"] is False
    app.state.self_discovery_engine = None
    assert client.post("/api/evolution/discovery/run", headers=headers).status_code == 503
