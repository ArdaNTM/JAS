"""Regression: unprovisioned Owner CLI never creates keys or executes approvals."""
from __future__ import annotations

import sys
import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

# The standalone script is intentionally not an importable runtime package.
_CLI_PATH = Path(__file__).resolve().parents[1] / "scripts" / "start_owner_control_plane.py"
_CLI_SPEC = importlib.util.spec_from_file_location("aura_owner_cli_test", _CLI_PATH)
assert _CLI_SPEC is not None and _CLI_SPEC.loader is not None
owner_cli = importlib.util.module_from_spec(_CLI_SPEC)
_CLI_SPEC.loader.exec_module(owner_cli)


def _run_cli(monkeypatch, args):
    captured = {}
    monkeypatch.setattr(sys, "argv", ["start_owner_control_plane.py", *args])
    def run(app, **kwargs):
        captured["app"] = app
        captured["options"] = kwargs
    monkeypatch.setattr("uvicorn.run", run)
    owner_cli.main()
    return captured


def test_unenrolled_owner_cli_defaults_to_loopback_read_only(monkeypatch, tmp_path):
    root = tmp_path / "Evolution"
    root.mkdir()
    monkeypatch.setenv("AURA_EVOLUTION_ROOT", str(root))
    result = _run_cli(monkeypatch, [])
    assert result["options"]["host"] == "127.0.0.1"
    assert result["options"]["port"] == 8766
    assert result["options"]["workers"] == 1
    assert not (root / "owner" / "owner-passkey.json").exists()
    assert not (root / "owner" / "approvals.sqlite").exists()

    with TestClient(result["app"], base_url="http://localhost:8766") as client:
        assert client.get("/health", headers={"Host": "127.0.0.1:8766"}).status_code == 200
        assert client.get("/api/owner/health").json()["approval_auth"] == "not_provisioned"
        assert client.get("/api/owner/discoveries").status_code == 200
        assert client.post("/api/owner/challenge",
                           json={"approval_id": "x"},
                           headers={"Origin": "http://localhost:8766"}).status_code == 503
        assert client.post("/api/owner/decision", json={
            "challenge_id": "a" * 36, "credential_id": "x",
            "client_data_json": "x", "authenticator_data": "x",
            "signature": "x", "decision": "approved",
        }, headers={"Origin": "http://localhost:8766"}).status_code == 503
        assert client.post("/api/owner/challenge", json={"approval_id": "x"},
                           headers={"Origin": "http://127.0.0.1:8766"}).status_code == 403


def test_owner_cli_does_not_mutate_unenrolled_provisioning(monkeypatch, tmp_path):
    root = tmp_path / "Evolution"
    state = root / "owner"
    state.mkdir(parents=True)
    original = b"existing private DB bytes must be preserved"
    (state / "approvals.sqlite").write_bytes(original)
    (state / "challenges.sqlite").write_bytes(original)
    monkeypatch.setenv("AURA_EVOLUTION_ROOT", str(root))
    result = _run_cli(monkeypatch, [])
    with TestClient(result["app"], base_url="http://localhost:8766") as client:
        assert client.get("/api/owner/health").json()["approval_auth"] == "not_provisioned"
    assert (state / "approvals.sqlite").read_bytes() == original
    assert (state / "challenges.sqlite").read_bytes() == original
    assert not (state / "owner-passkey.json").exists()


@pytest.mark.parametrize("args", [
    ["--require-enrollment"],
    ["--owner-config", "NOT_PRESENT"],
])
def test_explicit_owner_mode_never_silently_downgrades(monkeypatch, tmp_path, args):
    root = tmp_path / "Evolution"
    root.mkdir()
    monkeypatch.setenv("AURA_EVOLUTION_ROOT", str(root))
    with pytest.raises((ValueError, PermissionError), match="pre-provisioned"):
        _run_cli(monkeypatch, args)


def test_invalid_existing_passkey_is_not_downgraded(monkeypatch, tmp_path):
    root = tmp_path / "Evolution"
    state = root / "owner"
    state.mkdir(parents=True)
    (state / "owner-passkey.json").write_text("not valid JSON")
    monkeypatch.setenv("AURA_EVOLUTION_ROOT", str(root))
    with pytest.raises((ValueError, PermissionError)):
        _run_cli(monkeypatch, [])


def test_windows_launcher_health_is_exact_success_and_nonblocking():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    launcher = (root / "scripts" / "launch-aura-desktop.ps1").read_text("utf-8")
    assert 'http://127.0.0.1:8766/health' in launcher
    assert "-RequireOk" in launcher
    assert '$ownerWarning' in launcher
    assert 'Read-LogSafe -Path $OwnerLogErr' in launcher
    # Owner warning should not be raised into the outer Core/HUD teardown.
    assert "Open-AuraBrowser" in launcher
