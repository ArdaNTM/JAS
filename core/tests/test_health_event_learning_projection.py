"""Health projections must not invent operational components."""
from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from aura_core.application.health_api import router


def client(event_runtime=None, learning_scheduler=None, kernel=None):
    app = FastAPI()
    app.include_router(router)
    app.state.event_bus_runtime = event_runtime
    app.state.learning_scheduler = learning_scheduler
    app.state.kernel = kernel
    app.state.mcp_gateway = object()
    app.state.permission_engine = object()
    return TestClient(app)


def test_event_bus_running_and_learning_not_configured():
    runtime = SimpleNamespace(status=lambda: {"enabled": True, "running": True})
    kernel = SimpleNamespace(event_bus=object(), state="running")
    response = client(event_runtime=runtime, kernel=kernel).get("/api/health")
    assert response.status_code == 200
    components = response.json()["components"]
    assert components["event_bus"]["status"] == "running"
    assert components["learning"]["status"] == "not_configured"


def test_disabled_event_bus_and_stopped_learning_are_not_reported_healthy():
    runtime = SimpleNamespace(status=lambda: {"enabled": False, "running": False})
    scheduler = SimpleNamespace(running=False)
    kernel = SimpleNamespace(event_bus=object(), state="running")
    components = client(runtime, scheduler, kernel).get("/api/health").json()["components"]
    assert components["event_bus"]["status"] == "disabled"
    assert components["learning"]["status"] == "stopped"


def test_missing_event_bus_is_not_silently_reported_running():
    components = client().get("/api/health").json()["components"]
    assert components["event_bus"]["status"] == "not_configured"
    assert components["learning"]["status"] == "not_configured"
