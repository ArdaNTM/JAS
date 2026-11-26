"""Startup health must stay responsive during signed provider recovery."""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from aura_core.evolution import activation_runtime
from aura_core.evolution.activation_runtime import DelegatedMCPActivationManager
from test_evolution_autonomous_activation import FakeProvider, _kernel, _signed_fixture
from test_ui_contract import make_client


@pytest.mark.parametrize("phase", ["grant", "pending", "runtime_tree"])
def test_real_health_endpoint_responds_while_signed_recovery_waits(tmp_path, monkeypatch, phase):
    workspace, _, repo = _signed_fixture(tmp_path, monkeypatch)
    kernel, _ = _kernel()

    async def factory(*args):
        return FakeProvider()

    manager = DelegatedMCPActivationManager(
        workspace=workspace, kernel=kernel, provider_factory=factory,
    )
    entered = threading.Event()
    release = threading.Event()

    if phase == "grant":
        target, name = manager.delegation, "verified_grant"
    elif phase == "pending":
        target, name = manager.decisions, "evaluate_pending"
    else:
        target, name = activation_runtime, "runtime_fingerprint"
    original = getattr(target, name)

    def delayed(*args, **kwargs):
        entered.set()
        if not release.wait(8):
            raise AssertionError("Signed verification blocked the HTTP event loop")
        return original(*args, **kwargs)

    monkeypatch.setattr(target, name, delayed)
    app = make_client().app

    async def scenario():
        scan = asyncio.create_task(manager.scan(limit=1))
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1",
            ) as client:
                response = await asyncio.wait_for(client.get("/health"), timeout=3)
                assert response.status_code == 200
                assert response.json() == {"status": "ok"}
                assert not scan.done(), "Health must respond before verification finishes"
        finally:
            release.set()
            try:
                assert await scan == [repo]
            finally:
                await manager.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("enabled", ["0", "1"])
def test_composed_lifespan_starts_only_opted_in_review_and_stops_it(tmp_path, monkeypatch, enabled):
    monkeypatch.chdir(tmp_path)
    for name, value in {
        "LOCALAPPDATA": str(tmp_path),
        "AURA_STORAGE_MODE": "local",
        "AURA_DISABLE_EXTERNAL_PROVIDERS": "1",
        "AURA_SELF_DISCOVERY_ENABLED": "0",
        "AURA_EVOLUTION_AUTO_ACTIVATE": "0",
        "AURA_BACKGROUND_THINKING_ENABLED": "0",
        "AURA_EVOLUTION_REVIEW_ENABLED": enabled,
        "AURA_EVOLUTION_INTROSPECTION_ENABLED": "0",
        "AURA_EVOLUTION_SELF_PATCH_ENABLED": "0",
        "AURA_JAS_ROOT": str(Path(__file__).resolve().parents[2]),
        "AURA_API_BEARER_TOKEN": "t" * 40,
        "AURA_API_PRINCIPAL_ID": "local_owner",
        "AURA_STAGE_C_ENABLED": "0",
        "AURA_STAGE_C_BROWSER_ENABLED": "0",
    }.items():
        monkeypatch.setenv(name, value)
    from aura_core.main import build_app

    app = build_app()
    worker = app.state.evolution_review
    assert (worker is not None) == (enabled == "1")
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        if worker is not None:
            assert worker.status()["enabled"] is True
            assert worker.status()["can_execute"] is False
    if worker is not None:
        assert worker.status()["enabled"] is False


def test_production_lifespan_does_not_drop_review_lifecycle():
    # Protect the production branch as well as the actual composed
    # provider-disabled lifecycle exercised above.
    source = (Path(__file__).resolve().parents[1] / "src/aura_core/main.py").read_text("utf-8")
    startup = source.split("# This composition replaces create_api's lifespan.", 1)[1]
    startup, shutdown = startup.split("AURA LIFESPAN SHUTDOWN BEGIN", 1)
    assert 'getattr(_app.state, "evolution_review", None)' in startup
    assert "local_evolution.start()" in startup
    assert 'getattr(app.state, "evolution_review", None)' in shutdown
    assert "await local_evolution.stop()" in shutdown
