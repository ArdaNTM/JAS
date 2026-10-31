"""Standalone activation API never bypasses independent attestations or owner proof."""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from aura_core.evolution.activation_api import create_governed_activation_app
from aura_core.evolution.owner_receipt import DurableOwnerReceiptConsumer
from aura_core.evolution.skill_registry import GovernedSkillRegistry


@pytest.fixture
def api():
    owner = MagicMock(spec=DurableOwnerReceiptConsumer)
    registry = MagicMock(spec=GovernedSkillRegistry)
    registry._owner = owner
    registry._signed = lambda binding, receipt: True
    registry.activate.return_value = "validated-rev-1"
    registry.rollback.return_value = "previous-rev"
    app = create_governed_activation_app(registry=registry, owner_receipts=owner)
    with TestClient(app, base_url="http://localhost:8767") as client:
        yield client, registry


def change(client, *, operation="activate", origin="http://localhost:8766", **extra):
    return client.post("/api/activation/version", json={
        "name": "safe_skill", "action": operation, "owner_receipt": "signed-receipt",
        **extra,
    }, headers={"Origin": origin, "Sec-Fetch-Site": "same-site"})


def test_signed_guards_required_to_construct_activation_api():
    owner = MagicMock(spec=DurableOwnerReceiptConsumer)
    registry = MagicMock(spec=GovernedSkillRegistry)
    registry._owner = owner
    registry._signed = None
    with pytest.raises(PermissionError):
        create_governed_activation_app(registry=registry, owner_receipts=owner)
    registry._signed = lambda binding, receipt: True
    registry._owner = MagicMock(spec=DurableOwnerReceiptConsumer)
    with pytest.raises(PermissionError):
        create_governed_activation_app(registry=registry, owner_receipts=owner)


def test_activation_version_switches_only_metadata(api):
    client, registry = api
    r = change(client)
    assert r.status_code == 200
    assert r.json()["revision"] == "validated-rev-1"
    assert r.json()["tool_executed"] is False
    assert r.json()["generated_python_loaded"] is False
    registry.activate.assert_called_once_with(
        "safe_skill", principal_id="local_owner", owner_receipt="signed-receipt",
    )
    r = change(client, operation="rollback")
    assert r.status_code == 200
    registry.rollback.assert_called_once()
    r = change(client, operation="revoke")
    assert r.status_code == 200
    assert r.json()["revision"] is None
    registry.revoke.assert_called_once()


def test_rejected_by_registry_stays_denied(api):
    client, registry = api
    registry.activate.side_effect = PermissionError("sandbox or owner verification failed")
    response = change(client)
    assert response.status_code == 403
    assert "sandbox" not in response.text


def test_cross_origin_wrong_host_and_invalid_shape_fail(api):
    client, registry = api
    assert change(client, origin="http://127.0.0.1:5173").status_code == 403
    assert change(client, origin="https://evil.invalid").status_code == 403
    assert client.post("/api/activation/version", json={
        "name": "safe_skill", "action": "activate", "owner_receipt": "x",
    }).status_code == 403
    assert client.post("/api/activation/version", json={
        "name": "safe_skill", "action": "activate", "owner_receipt": "x",
    }, headers={"Origin": "http://localhost:8766", "Host": "evil.example"}).status_code == 403
    assert change(client, name="bad/path").status_code == 422
    assert change(client, extra="attempt").status_code == 422
    assert change(client, operation="import_python").status_code == 422
    registry.activate.assert_not_called()
