"""Regression for missing WS secret during the real AURA Core composition.

The WebSocket ticket issuer is optional. Missing credentials disable ticket
issuance, never the authenticated capability catalog or Kernel/Gateway.
Configured but weak credentials must still fail closed.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from aura_core.application.composition import create_composed_app
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig
from aura_core.security.ws_ticket import WebSocketTicketManager


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "core"
OWNER_TOKEN = "owner-local-capability-center-token-1234567890"


def _app():
    return create_composed_app(
        config=RuntimeConfig(runtime="ollama", model="test", temperature=0, max_tokens=64),
        backend_config=BackendConfig(endpoint="http://127.0.0.1:11434", timeout=1),
    )


def test_missing_ws_token_is_optional_for_http_but_has_no_ticket_issuer(monkeypatch):
    monkeypatch.delenv("AURA_EVENT_STREAM_TOKEN", raising=False)
    app = _app()
    assert app.state.ws_ticket_manager is None


def test_nonempty_weak_ws_token_still_fails_closed(monkeypatch):
    monkeypatch.setenv("AURA_EVENT_STREAM_TOKEN", "short")
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        _app()


def test_valid_ws_secret_retains_one_time_hmac_ticket_guard(monkeypatch):
    monkeypatch.setenv("AURA_EVENT_STREAM_TOKEN", "s" * 48)
    app = _app()
    manager = app.state.ws_ticket_manager
    assert isinstance(manager, WebSocketTicketManager)
    ticket = manager.issue()
    assert manager.verify(ticket.value)
    assert not manager.verify(ticket.value)
    assert not manager.verify("attacker-supplied-ticket")


def test_real_core_import_and_live_testclient_center_200_without_ws_token(tmp_path):
    """Import exactly as Windows user does, starting from core cwd.

    Child process isolates module-level "app = build_app()" so it cannot
    accidentally reuse a previously configured token from another test.
    """
    child_env = os.environ.copy()
    child_env.pop("AURA_EVENT_STREAM_TOKEN", None)
    child_env.update({
        "AURA_STORAGE_MODE": "local",
        "AURA_DISABLE_EXTERNAL_PROVIDERS": "1",
        "AURA_TELEMETRY_DAEMON_ENABLED": "0",
        "AURA_BACKGROUND_THINKING_ENABLED": "0",
        "AURA_EVOLUTION_REVIEW_ENABLED": "0",
        "AURA_API_BEARER_TOKEN": OWNER_TOKEN,
        "AURA_API_PRINCIPAL_ID": "local_owner",
        "AURA_CORE_PORT": "8000",
        "AURA_TASK_DB_PATH": str(tmp_path / "tasks.sqlite3"),
        "AURA_WORKFLOW_DB_PATH": str(tmp_path / "workflows.sqlite3"),
        "AURA_GRAPH_DB_PATH": str(tmp_path / "graph.sqlite3"),
    })
    code = """
from fastapi.testclient import TestClient
from aura_core.main import build_app

app = build_app()
assert app.state.ws_ticket_manager is None
assert app.state.mcp_gateway is not None
assert app.state.kernel.permission_engine is not None
before = app.state.kernel.permission_engine.integrity_digest()
with TestClient(app, base_url="http://127.0.0.1:8000",
                client=("127.0.0.1", 50000)) as client:
    response = client.get(
        "/api/capabilities/center",
        headers={"Authorization": "Bearer " + TOKEN},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["feature_count"] == 117
    assert len(payload["features"]) == 117
    assert all(item["status"] == "source_complete_bounded_v1"
               for item in payload["features"])
    assert client.get("/api/capabilities/center").status_code == 401
    no_ws_secret = client.post("/api/ws/ticket")
    assert no_ws_secret.status_code == 503, no_ws_secret.text
    assert "ticket" not in no_ws_secret.text
    assert app.state.kernel.permission_engine.integrity_digest() == before
print("PASS: Core app booted without WS secret; GET /api/capabilities/center 200; WS issuer 503")
""".replace("TOKEN", repr(OWNER_TOKEN))
    process = subprocess.run(
        [sys.executable, "-c", code], cwd=CORE, env=child_env,
        capture_output=True, text=True, timeout=75, check=False,
    )
    assert process.returncode == 0, (process.stderr[-3500:] + "\n" + process.stdout[-700:])
    assert "GET /api/capabilities/center 200" in process.stdout
