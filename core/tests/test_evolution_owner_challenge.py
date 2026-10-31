"""Trusted owner decision path: WebAuthn challenge bound to approval record."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from aura_core.enterprise.approval_store import ApprovalStatus, SQLiteApprovalStore
from aura_core.evolution.owner_challenge import TrustedOwnerPasskeyDecider
from aura_core.evolution.owner_passkey import OwnerPasskeyVerifier, WebAuthnOwnerAssertion


def _digest(b):
    return hashlib.sha256(b).hexdigest()


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


@pytest.fixture
def owner_session(tmp_path):
    key = ec.generate_private_key(ec.SECP256R1())
    cred = os.urandom(32)
    verifier = OwnerPasskeyVerifier(
        rp_id="localhost", origin="http://localhost:5173",
        credential_id=_b64(cred),
        public_key_pem=key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        ),
    )
    db = tmp_path / "owner-auth.sqlite"
    sqlite3.connect(db).close()
    db.chmod(0o600)
    policy = _digest(b"pinned-policy")
    approvals = SQLiteApprovalStore(":memory:")
    def create_approval(operation="activate", capability="GovernedSkillActivation"):
        fingerprint = _digest(b"skill-binding-review")
        return approvals.create(
            principal_id="local_owner", capability_id=capability,
            operation_id=operation, resource_scope="evolution:skill:" + fingerprint,
            request_fingerprint=fingerprint, policy_digest=policy,
        )
    def assertion(challenge, *, counter=1, origin="http://localhost:5173"):
        raw = base64.urlsafe_b64decode(challenge["challenge"] + "==")
        client = json.dumps(
            {"type": "webauthn.get", "challenge": _b64(raw), "origin": origin,
             "crossOrigin": False},
            separators=(",", ":"),
        ).encode()
        auth = hashlib.sha256(b"localhost").digest() + b"\x05" + counter.to_bytes(4, "big")
        signature = key.sign(auth + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        return WebAuthnOwnerAssertion(
            credential_id=_b64(cred), client_data_json=_b64(client),
            authenticator_data=_b64(auth), signature=_b64(signature),
        )
    yield db, approvals, verifier, policy, _b64(cred), create_approval, assertion
    approvals.close()


def _service(session):
    db, approvals, verifier, policy, cred, _, _ = session
    return TrustedOwnerPasskeyDecider(
        database_path=db, owner_verifier=verifier,
        approvals=approvals, policy_digest=policy, credential_id=cred,
    )


def test_trusted_owner_approval_binds_record_and_consumes_challenge_once(owner_session):
    _, approvals, _, _, _, create, sign = owner_session
    record = create()
    with _service(owner_session) as service:
        challenge = service.issue(record.approval_id)
        assert challenge["user_verification"] == "required"
        assertion = sign(challenge, counter=3)
        updated = service.decide(challenge_id=challenge["challenge_id"], assertion=assertion)
        assert updated.status is ApprovalStatus.APPROVED
        assert updated.approver_id == "human:local-owner"
        with pytest.raises(PermissionError):
            service.decide(challenge_id=challenge["challenge_id"], assertion=assertion)
    with _service(owner_session) as restarted:
        with pytest.raises(PermissionError):
            restarted.decide(challenge_id=challenge["challenge_id"], assertion=assertion)
        with pytest.raises(PermissionError):
            restarted.issue(record.approval_id)


def test_passkey_owner_denial_and_signature_failure_are_fail_closed(owner_session):
    _, approvals, _, _, _, create, sign = owner_session
    record = create()
    with _service(owner_session) as service:
        first = service.issue(record.approval_id)
        with pytest.raises(PermissionError):
            service.decide(challenge_id=first["challenge_id"],
                           assertion=sign(first, origin="http://evil.example"))
        assert approvals.get(record.approval_id).status is ApprovalStatus.PENDING
        denied = service.decide(
            challenge_id=first["challenge_id"], assertion=sign(first, counter=1),
            decision=ApprovalStatus.DENIED,
        )
        assert denied.status is ApprovalStatus.DENIED
        with pytest.raises(PermissionError):
            service.issue(record.approval_id)


def test_cross_approval_replay_and_counter_rollback_rejected(owner_session):
    _, approvals, _, _, _, create, sign = owner_session
    old = create()
    newer = create()
    with _service(owner_session) as service:
        old_challenge = service.issue(old.approval_id)
        new_challenge = service.issue(newer.approval_id)
        with pytest.raises(PermissionError):
            service.decide(challenge_id=new_challenge["challenge_id"],
                           assertion=sign(old_challenge, counter=10))
        service.decide(challenge_id=old_challenge["challenge_id"],
                       assertion=sign(old_challenge, counter=10))
        with pytest.raises(PermissionError):
            service.decide(challenge_id=new_challenge["challenge_id"],
                           assertion=sign(new_challenge, counter=9))
        assert approvals.get(newer.approval_id).status is ApprovalStatus.PENDING
        service.decide(challenge_id=new_challenge["challenge_id"],
                       assertion=sign(new_challenge, counter=11))
        assert approvals.get(newer.approval_id).status is ApprovalStatus.APPROVED


def test_owner_challenge_denies_non_governed_approval(owner_session):
    _, approvals, _, _, _, create, sign = owner_session
    record = create(capability="OtherCapability")
    with _service(owner_session) as service:
        with pytest.raises(PermissionError):
            service.issue(record.approval_id)
