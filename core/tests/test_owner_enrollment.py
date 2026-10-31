"""Yubico FIDO2 enrollment ceremony: real server-side WebAuthn validation."""
import base64
import hashlib
import json
import secrets

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient
import pytest

from aura_core.evolution.owner_enrollment import ProtectedEnrollment
from aura_core.evolution.owner_enrollment_http import create_enrollment_app
from aura_core.evolution.owner_passkey import OwnerPasskeyVerifier


def b64(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


@pytest.fixture
def setup(tmp_path):
    token = secrets.token_hex(32)
    policy = hashlib.sha256(b"pinned-JAS-policy").hexdigest()
    out = tmp_path / "credential.json"
    ceremony = ProtectedEnrollment(
        bootstrap_secret=token, config_output=out, policy_digest=policy,
    )
    return token, ceremony, out


def make_registration(options, *, origin="http://localhost:8766", rp="localhost",
                      flags=0x45, challenge=None, credential_id=None):
    from fido2 import cbor
    key = ec.generate_private_key(ec.SECP256R1())
    numbers = key.public_key().public_numbers()
    credential_id = credential_id or secrets.token_bytes(32)
    cose = {1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32, "big"),
            -3: numbers.y.to_bytes(32, "big")}
    authenticator = (
        hashlib.sha256(rp.encode()).digest() + bytes([flags]) +
        (0).to_bytes(4, "big") + bytes(16) +
        len(credential_id).to_bytes(2, "big") + credential_id + cbor.encode(cose)
    )
    attestation = cbor.encode({"fmt": "none", "authData": authenticator,
                               "attStmt": {}})
    client = json.dumps({
        "type": "webauthn.create",
        "challenge": challenge or options["publicKey"]["challenge"],
        "origin": origin,
        "crossOrigin": False,
    }, separators=(",", ":")).encode()
    return {
        "id": b64(credential_id), "rawId": b64(credential_id),
        "type": "public-key",
        "response": {
            "clientDataJSON": b64(client),
            "attestationObject": b64(attestation),
        },
        "clientExtensionResults": {},
    }


def test_yubico_registration_issues_one_time_config_verified_by_owner_passkey(setup):
    token, ceremony, output = setup
    options = ceremony.begin(token)
    assert options["publicKey"]["authenticatorSelection"]["userVerification"] == "required"
    assert not output.exists()
    result = ceremony.complete(token, make_registration(options))
    assert result["status"] == "enrolled"
    assert not result["tool_activated"]
    config = json.loads(output.read_text())
    OwnerPasskeyVerifier(
        rp_id=config["rp_id"], origin=config["origin"],
        credential_id=config["credential_id"],
        public_key_pem=config["public_key_pem"].encode(),
    )
    assert config["origin"] == "http://localhost:8766"
    with pytest.raises(PermissionError):
        ceremony.begin(token)


@pytest.mark.parametrize("change", [
    {"origin": "http://127.0.0.1:5173"},
    {"origin": "http://evil.invalid"},
    {"rp": "evil.invalid"},
    {"flags": 0x41},  # no user verification (UV)
    {"flags": 0x44},  # no user presence (UP)
    {"challenge": b64(secrets.token_bytes(32))},
])
def test_registration_rejects_invalid_origin_rp_presence_challenge(setup, change):
    token, ceremony, output = setup
    options = ceremony.begin(token)
    with pytest.raises((PermissionError, ValueError)):
        ceremony.complete(token, make_registration(options, **change))
    assert not output.exists()
    with pytest.raises(PermissionError):
        ceremony.complete(token, make_registration(options))


def test_enrollment_secret_and_previous_owner_config_fail_closed(setup):
    token, ceremony, output = setup
    with pytest.raises(PermissionError):
        ceremony.begin(secrets.token_hex(32))
    assert not output.exists()
    first = ceremony.begin(token)
    with pytest.raises(PermissionError):
        ceremony.begin(token)
    with pytest.raises(PermissionError):
        ceremony.complete("wrong-token", make_registration(first))
    ceremony.complete(token, make_registration(first))
    with pytest.raises(PermissionError):
        ProtectedEnrollment(bootstrap_secret=token, config_output=output,
                            policy_digest=hashlib.sha256(b"policy").hexdigest())


def test_enrollment_http_host_origin_json_and_secret_guards(setup):
    token, ceremony, output = setup
    with TestClient(create_enrollment_app(ceremony=ceremony),
                    base_url="http://localhost:8766") as client:
        assert client.get("/").status_code == 200
        assert "navigator.credentials.create" in client.get("/enroll.js").text
        assert client.post("/api/enrollment/begin", json={}).status_code == 403
        assert client.post("/api/enrollment/begin", json={}, headers={
            "Origin":"http://127.0.0.1:5173", "X-Aura-Bootstrap":token,
        }).status_code == 403
        assert client.post("/api/enrollment/begin", json={}, headers={
            "Origin":"http://localhost:8766", "X-Aura-Bootstrap":token,
            "Host":"evil.invalid",
        }).status_code == 403
        response=client.post("/api/enrollment/begin", json={}, headers={
            "Origin":"http://localhost:8766", "X-Aura-Bootstrap":token,
        })
        assert response.status_code == 200, response.text
        assert response.headers["Cache-Control"] == "no-store"
        created=client.post("/api/enrollment/complete", json={
            "response":make_registration(response.json()),
        }, headers={"Origin":"http://localhost:8766","X-Aura-Bootstrap":token})
        assert created.status_code == 200, created.text
