from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from aura_core.security.http_auth import (
    authenticated_principal,
    load_http_auth_config,
)


def _client(token: str | None = "t" * 40, principal: str = "local_owner") -> TestClient:
    app = FastAPI()
    app.state.http_bearer_token = token
    app.state.http_principal_id = principal

    @app.get("/protected")
    def protected(principal_id: str = Depends(authenticated_principal)):
        return {"principal_id": principal_id}

    return TestClient(app)


def test_missing_bearer_is_rejected():
    response = _client().get("/protected")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_invalid_bearer_is_rejected():
    response = _client().get(
        "/protected",
        headers={"Authorization": "Bearer " + "x" * 40},
    )
    assert response.status_code == 401


def test_principal_is_server_configured_not_client_supplied():
    response = _client(principal="configured-principal").get(
        "/protected",
        headers={"Authorization": "Bearer " + "t" * 40},
    )
    assert response.status_code == 200
    assert response.json() == {"principal_id": "configured-principal"}


def test_missing_auth_configuration_fails_closed():
    response = _client(token=None).get(
        "/protected",
        headers={"Authorization": "Bearer " + "t" * 40},
    )
    assert response.status_code == 503


def test_auth_config_requires_strong_configured_token(monkeypatch):
    import pytest

    monkeypatch.setenv("AURA_API_BEARER_TOKEN", "short")
    monkeypatch.setenv("AURA_API_PRINCIPAL_ID", "local_owner")
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        load_http_auth_config()


def test_auth_config_defaults_to_local_owner_when_token_is_absent(monkeypatch):
    monkeypatch.delenv("AURA_API_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("AURA_API_PRINCIPAL_ID", raising=False)
    assert load_http_auth_config() == (None, "local_owner")
