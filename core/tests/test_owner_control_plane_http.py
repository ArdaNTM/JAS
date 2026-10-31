"""Owner-control-plane HTTP security, native passkey authorization and UI tests."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
import pytest

from aura_core.enterprise.approval_store import SQLiteApprovalStore, ApprovalStatus
from aura_core.evolution.owner_challenge import TrustedOwnerPasskeyDecider
from aura_core.evolution.owner_control_plane import create_owner_control_plane
from aura_core.evolution.owner_passkey import OwnerPasskeyVerifier


def b64(x: bytes) -> str:
    return base64.urlsafe_b64encode(x).decode().rstrip("=")


@pytest.fixture
def owner(tmp_path):
    key = ec.generate_private_key(ec.SECP256R1())
    cred = os.urandom(32)
    origin = "http://localhost:8766"
    verifier = OwnerPasskeyVerifier(
        rp_id="localhost", origin=origin, credential_id=b64(cred),
        public_key_pem=key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        ),
    )
    db = tmp_path / "challenge.sqlite"
    sqlite3.connect(db).close()
    db.chmod(0o600)
    store = SQLiteApprovalStore(":memory:")
    policy = hashlib.sha256(b"pinned-policy").hexdigest()
    decider = TrustedOwnerPasskeyDecider(
        database_path=db, owner_verifier=verifier,
        approvals=store, policy_digest=policy, credential_id=b64(cred),
    )

    def pending(capability="GovernedSkillActivation", operation="activate"):
        binding = hashlib.sha256(b"reviewed-binding").hexdigest()
        return store.create(
            principal_id="local_owner", capability_id=capability,
            operation_id=operation, resource_scope="evolution:skill:" + binding,
            request_fingerprint=binding, policy_digest=policy,
        )

    def assertion(challenge, *, counter=1, origin=origin, flags=5):
        client_data = json.dumps({
            "type": "webauthn.get", "challenge": challenge["challenge"],
            "origin": origin, "crossOrigin": False,
        }, separators=(",", ":")).encode()
        auth = hashlib.sha256(b"localhost").digest() + bytes([flags]) + counter.to_bytes(4, "big")
        signature = key.sign(auth + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        return {
            "challenge_id": challenge["challenge_id"], "credential_id": b64(cred),
            "client_data_json": b64(client_data),
            "authenticator_data": b64(auth), "signature": b64(signature),
            "decision": "approved",
        }

    app = create_owner_control_plane(approvals=store, decider=decider)
    with TestClient(app, base_url=origin) as client:
        yield client, store, pending, assertion
    store.close()
    decider.close()


def post(client, path, data, origin="http://localhost:8766", **headers):
    return client.post(path, json=data, headers={"Origin": origin, **headers})


def test_trusted_owner_review_page_and_host_fail_closed(owner):
    client, store, pending, assertion = owner
    html = client.get("/")
    assert html.status_code == 200
    assert "Trusted Owner Review" in html.text
    assert "script-src 'self'" in html.headers["Content-Security-Policy"]
    assert html.headers["X-Frame-Options"] == "DENY"
    js = client.get("/app.js")
    assert js.status_code == 200
    assert "navigator.credentials.get" in js.text
    assert "userVerification: \"required\"" in js.text
    assert client.get("/", headers={"Host": "127.0.0.1:8766"}).status_code == 403
    health = client.get("/api/owner/health")
    assert health.json()["activation_allowed"] is False


def test_owner_approval_requires_signed_passkey_and_exact_origin(owner):
    client, store, pending, assertion = owner
    record = pending()
    listed = client.get("/api/owner/pending")
    assert len(listed.json()["items"]) == 1
    assert listed.json()["items"][0]["request_fingerprint"] == record.request_fingerprint
    payload = {"approval_id": record.approval_id}
    assert client.post("/api/owner/challenge", json=payload).status_code == 403
    assert post(client, "/api/owner/challenge", payload, "http://127.0.0.1:5173").status_code == 403
    assert post(client, "/api/owner/challenge", payload, **{"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.post("/api/owner/challenge", data="approval_id=x",
                       headers={"Origin": "http://localhost:8766",
                                "Content-Type": "text/plain"}).status_code == 415
    issued = post(client, "/api/owner/challenge", payload)
    assert issued.status_code == 200, issued.text
    challenge = issued.json()
    assert challenge["rp_id"] == "localhost"
    assert challenge["user_verification"] == "required"
    result = assertion(challenge)
    assert post(client, "/api/owner/decision", {
        **result, "signature": "invalid", "decision": "approved",
    }).status_code == 409
    assert store.get(record.approval_id).status is ApprovalStatus.PENDING
    approved = post(client, "/api/owner/decision", result)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["activation_performed"] is False
    assert approved.json()["tool_executed"] is False
    assert store.get(record.approval_id).approver_id == "human:local-owner"
    assert post(client, "/api/owner/decision", result).status_code == 409


def test_owner_denial_is_also_passkey_verified(owner):
    client, store, pending, assertion = owner
    record = pending(operation="rollback")
    challenge = post(client, "/api/owner/challenge", {"approval_id": record.approval_id}).json()
    proof = assertion(challenge)
    proof["decision"] = "denied"
    result = post(client, "/api/owner/decision", proof)
    assert result.status_code == 200
    assert result.json()["status"] == "denied"
    assert store.get(record.approval_id).status is ApprovalStatus.DENIED


def test_non_governed_pending_approval_never_enters_owner_ui(owner):
    client, store, pending, assertion = owner
    other = pending(capability="UnrelatedCapability")
    assert client.get("/api/owner/pending").json()["items"] == []
    response = post(client, "/api/owner/challenge", {"approval_id": other.approval_id})
    assert response.status_code == 409
    assert store.get(other.approval_id).status is ApprovalStatus.PENDING
