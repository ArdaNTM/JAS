"""Security regression for read-only policy decisions and explicit Owner delegation."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from aura_core.evolution.decision_engine import (
    AutonomousDelegationVerifier, EvolutionDecisionEngine, _canonical,
)
from aura_core.evolution.external_staging import EvolutionWorkspace


@pytest.fixture
def sample(tmp_path):
    workspace = EvolutionWorkspace(tmp_path / "evolution")
    package = workspace.root / "verified" / "test__local-memory"
    package.mkdir()
    source = b"static review snapshot; no import or execution"
    digest = hashlib.sha256(source).hexdigest()
    (package / "source.zip").write_bytes(source)
    (package / "aura-capability-manifest.json").write_text(json.dumps({
        "repository": "test/local-memory",
        "source_sha256": digest,
        "status": "READY_FOR_OWNER_REVIEW",
        "license_spdx_metadata": "MIT",
        "entrypoint_hint": "server.py",
        "detected_capabilities": ["FastMCP", "sqlite3"],
        "sandbox_attested": False,
        "owner_approved": False,
        "activation_performed": False,
        "execution_allowed": False,
    }), "utf-8")
    return workspace, package


def _signed_owner_delegation(workspace, monkeypatch, *, category="local_memory", expiry=None):
    signer = Ed25519PrivateKey.generate()
    pub = signer.public_key()
    raw = pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    owner = workspace.root / "owner"
    owner.mkdir(exist_ok=True)
    (owner / "autonomous_delegation.pub.pem").write_bytes(
        pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    now = int(time.time())
    claims = {
        "schema": "aura.owner-autonomy-delegation.v1",
        "principal_id": "local_owner",
        "issued_at": now - 10,
        "expires_at": expiry if expiry is not None else now + 600,
        "categories": [category],
        "scope": "static-review-only",
        "auto_activation": False,
    }
    signature = signer.sign(_canonical(claims))
    data = {
        "claims": claims,
        "signature_b64": base64.urlsafe_b64encode(signature).decode().rstrip("="),
    }
    (owner / "autonomous_delegation.json").write_text(json.dumps(data), "utf-8")
    monkeypatch.setenv("AURA_EVOLUTION_DELEGATION_KEY_SHA256", hashlib.sha256(raw).hexdigest())
    return data


@pytest.mark.parametrize("auto_flag,storage_mode", [
    ("0", "local"), ("1", "remote"), ("", "local"),
])
def test_default_mode_rejects_automated_authority(sample, monkeypatch, auto_flag, storage_mode):
    workspace, package = sample
    monkeypatch.setenv("AURA_EVOLUTION_AUTO_ACTIVATE", auto_flag)
    monkeypatch.setenv("AURA_STORAGE_MODE", storage_mode)
    outcome = EvolutionDecisionEngine(workspace).evaluate("test__local-memory")
    assert outcome.status == "OWNER_DELEGATION_REQUIRED"
    assert outcome.activation_performed is False
    assert outcome.registration_performed is False
    assert json.loads(workspace.active.read_text("utf-8"))["active"] == []


def test_flag_alone_or_unsigned_json_never_enables_authority(sample, monkeypatch):
    workspace, _ = sample
    monkeypatch.setenv("AURA_STORAGE_MODE", "local")
    monkeypatch.setenv("AURA_EVOLUTION_AUTO_ACTIVATE", "1")
    assert EvolutionDecisionEngine(workspace).evaluate("test__local-memory").status == "OWNER_DELEGATION_REQUIRED"
    owner = workspace.root / "owner"
    owner.mkdir()
    (owner / "autonomous_delegation.json").write_text('{"auto_activate":true}')
    assert EvolutionDecisionEngine(workspace).evaluate("test__local-memory").status == "OWNER_DELEGATION_REQUIRED"


def test_valid_signed_delegation_only_unlocks_review_decision(sample, monkeypatch):
    workspace, _ = sample
    monkeypatch.setenv("AURA_STORAGE_MODE", "local")
    monkeypatch.setenv("AURA_EVOLUTION_AUTO_ACTIVATE", "1")
    _signed_owner_delegation(workspace, monkeypatch)
    engine = EvolutionDecisionEngine(workspace)
    result = engine.evaluate("test__local-memory")
    assert result.status == "POLICY_ELIGIBLE_PENDING_ATTESTATION"
    assert result.benefit_score >= 60
    assert result.category == "local_memory"
    assert result.requires_owner_receipt is True
    assert result.requires_independent_attestation is True
    assert result.activation_performed is False
    assert engine.evaluate_pending()[0] == result
    assert json.loads(workspace.active.read_text())["active"] == []


def test_tampering_expiry_wrong_pubkey_or_scope_fails_closed(sample, monkeypatch):
    workspace, _ = sample
    monkeypatch.setenv("AURA_STORAGE_MODE", "local")
    monkeypatch.setenv("AURA_EVOLUTION_AUTO_ACTIVATE", "1")
    data = _signed_owner_delegation(workspace, monkeypatch)
    declaration = workspace.root / "owner" / "autonomous_delegation.json"
    engine = EvolutionDecisionEngine(workspace)
    assert engine.delegations.authorized_categories() == frozenset({"local_memory"})
    data["claims"]["scope"] = "activate-without-owner-receipt"
    declaration.write_text(json.dumps(data))
    assert not engine.delegations.authorized_categories()
    _signed_owner_delegation(workspace, monkeypatch, expiry=int(time.time()) - 1)
    assert not engine.delegations.authorized_categories()
    _signed_owner_delegation(workspace, monkeypatch)
    monkeypatch.setenv("AURA_EVOLUTION_DELEGATION_KEY_SHA256", "0" * 64)
    assert not engine.delegations.authorized_categories()


def test_evidence_tampering_or_active_duplicate_is_never_registered(sample, monkeypatch):
    workspace, package = sample
    engine = EvolutionDecisionEngine(workspace)
    assert engine.evaluate(
        "test__local-memory", active_categories=frozenset({"local_memory"})
    ).status == "DUPLICATE_CAPABILITY"
    (package / "source.zip").write_bytes(b"tampered")
    assert engine.evaluate("test__local-memory").status == "REJECTED_EVIDENCE"
    assert json.loads(workspace.active.read_text())["active"] == []


def test_untrusted_manifest_never_auto_registered_despite_flag(sample, monkeypatch):
    workspace, package = sample
    monkeypatch.setenv("AURA_STORAGE_MODE", "local")
    monkeypatch.setenv("AURA_EVOLUTION_AUTO_ACTIVATE", "1")
    _signed_owner_delegation(workspace, monkeypatch)
    manifest = package / "aura-capability-manifest.json"
    data = json.loads(manifest.read_text())
    data["owner_approved"] = True
    data["activation_performed"] = True
    manifest.write_text(json.dumps(data), "utf-8")
    outcome = EvolutionDecisionEngine(workspace).evaluate("test__local-memory")
    assert outcome.status == "REJECTED_EVIDENCE"
    assert json.loads(workspace.active.read_text())["active"] == []


def test_launcher_cannot_self_provision_owner_delegation():
    root = Path(__file__).resolve().parents[2]
    launcher = (root / "scripts" / "launch-aura-desktop.ps1").read_text("utf-8")
    assert 'autonomous_delegation.json' not in launcher
    assert 'AURA_EVOLUTION_AUTO_ACTIVATE' not in launcher


def test_local_authenticated_advisory_endpoint_never_activates(sample):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from aura_core.evolution.self_discovery_api import router
    from aura_core.security.http_auth import authenticated_principal
    workspace, _ = sample
    app = FastAPI()
    app.include_router(router)
    app.state.storage_mode = "local"
    app.state.self_discovery = type("Discovery", (), {"workspace": workspace})()
    app.dependency_overrides[authenticated_principal] = lambda: "local_owner"
    with TestClient(app, base_url="http://localhost:8000") as client:
        response = client.get("/api/evolution/discovery/decisions")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["items"]) == 1
        assert payload["items"][0]["status"] == "OWNER_DELEGATION_REQUIRED"
        assert payload["owner_receipt_required"] is True
        assert payload["activation_performed"] is False
    assert json.loads(workspace.active.read_text())["active"] == []


def test_advisory_endpoint_not_available_in_remote_mode(sample):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from aura_core.evolution.self_discovery_api import router
    from aura_core.security.http_auth import authenticated_principal
    workspace, _ = sample
    app = FastAPI()
    app.include_router(router)
    app.state.storage_mode = "remote"
    app.state.self_discovery = type("Discovery", (), {"workspace": workspace})()
    app.dependency_overrides[authenticated_principal] = lambda: "local_owner"
    with TestClient(app) as client:
        assert client.get("/api/evolution/discovery/decisions").status_code == 503
