"""Durable replay state and ES256 WebAuthn owner verification tests."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import time
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

from aura_core.evolution.durable_attestation import DurableAttestationReceiptRegistry
from aura_core.evolution.sandbox_attestor import (
    DOMAIN, SandboxClaims, SignedSandboxAttestation, canonical_claims,
    IndependentAttestationVerifier,
)
from aura_core.evolution.owner_passkey import OwnerPasskeyVerifier, WebAuthnOwnerAssertion


def digest(x: bytes) -> str:
    return hashlib.sha256(x).hexdigest()


def b64(x: bytes) -> str:
    return base64.urlsafe_b64encode(x).rstrip(b"=").decode("ascii")


class Binding:
    source_sha256 = digest(b"candidate-source")
    review_digest = digest(b"reviewed-full-capability-binding")


@pytest.fixture
def attestor():
    key = ed25519.Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    now = int(time.time())
    claims = SandboxClaims(
        source_sha256=Binding.source_sha256, tests_sha256=digest(b"test-suite"),
        image_digest="sha256:" + digest(b"container-image"),
        policy_sha256=digest(b"network-off;readonly"),
        binding_digest=Binding.review_digest,
        run_id="trusted-run-0000001", runner_id="separate-runner",
        issued_at=now-1, expires_at=now+240, exit_code=0, outcome="passed",
        network_disabled=True, rootfs_readonly=True,
    )
    signature = base64.b64encode(key.sign(DOMAIN+canonical_claims(claims))).decode("ascii")
    proof = SignedSandboxAttestation(
        key_id="owner-attestor", claims=claims, signature_b64=signature,
    )
    verifier = IndependentAttestationVerifier(
        trusted_public_keys={"owner-attestor": pub},
        expected_image_digest=claims.image_digest,
        expected_policy_sha256=claims.policy_sha256,
        expected_tests_sha256=claims.tests_sha256, trusted_runner_id=claims.runner_id,
    )
    return proof, verifier


def _db_path(tmp_path):
    db = tmp_path / "trusted-attestation.sqlite"
    connection = sqlite3.connect(db)
    connection.close()
    db.chmod(0o600)
    return db


def test_durable_replay_survives_restart_and_concurrent_connections(tmp_path, attestor):
    proof, verifier = attestor
    path = _db_path(tmp_path)
    with DurableAttestationReceiptRegistry(database_path=path, verifier=verifier) as first:
        receipt = first.register(proof, source_sha256=Binding.source_sha256,
                                 binding_digest=Binding.review_digest)
        assert first.verify_binding(Binding, receipt)
        with DurableAttestationReceiptRegistry(database_path=path, verifier=verifier) as second:
            assert second.verify_binding(Binding, receipt)
            with pytest.raises(PermissionError):
                second.register(proof, source_sha256=Binding.source_sha256,
                                binding_digest=Binding.review_digest)
    with DurableAttestationReceiptRegistry(database_path=path, verifier=verifier) as reopened:
        assert reopened.verify_binding(Binding, receipt)
        with pytest.raises(PermissionError):
            reopened.register(proof, source_sha256=Binding.source_sha256,
                              binding_digest=Binding.review_digest)
        assert not reopened.verify_binding(type("Other", (), {
            "source_sha256": digest(b"tampered"), "review_digest": Binding.review_digest,
        }), receipt)


def test_durable_registry_fails_closed_on_corruption_and_expiry(tmp_path, attestor, monkeypatch):
    proof, verifier = attestor
    path = _db_path(tmp_path)
    with DurableAttestationReceiptRegistry(database_path=path, verifier=verifier) as ledger:
        receipt = ledger.register(proof, source_sha256=Binding.source_sha256,
                                  binding_digest=Binding.review_digest)
        assert ledger.verify_binding(Binding, receipt)
        monkeypatch.setattr("aura_core.evolution.sandbox_attestor.time.time",
                            lambda: proof.claims.expires_at + 1)
        assert not ledger.verify_binding(Binding, receipt)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE attestation_receipts SET envelope = ? WHERE receipt = ?",
                   ('{"tampered":true}', receipt))
    with DurableAttestationReceiptRegistry(database_path=path, verifier=verifier) as ledger:
        assert not ledger.verify_binding(Binding, receipt)


def test_durable_registry_requires_preprovisioned_store(tmp_path, attestor):
    _, verifier = attestor
    with pytest.raises(ValueError):
        DurableAttestationReceiptRegistry(database_path=":memory:", verifier=verifier)
    with pytest.raises(FileNotFoundError):
        DurableAttestationReceiptRegistry(database_path=tmp_path/"missing.db", verifier=verifier)
    path = _db_path(tmp_path)
    link = tmp_path / "replay-link.sqlite"
    try:
        link.symlink_to(path)
    except OSError:
        pytest.skip("Symlinks unavailable")
    with pytest.raises(ValueError):
        DurableAttestationReceiptRegistry(database_path=link, verifier=verifier)


@pytest.fixture
def owner_auth():
    key = ec.generate_private_key(ec.SECP256R1())
    credential_id = os.urandom(32)
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    verifier = OwnerPasskeyVerifier(
        rp_id="localhost", origin="http://localhost:5173",
        credential_id=b64(credential_id), public_key_pem=public,
    )
    challenge = os.urandom(32)

    def create(*, origin="http://localhost:5173", flags=5, counter=1,
               issued_challenge=challenge, cross_origin=False, rp_id="localhost"):
        data = json.dumps({
            "type": "webauthn.get", "challenge": b64(issued_challenge),
            "origin": origin, "crossOrigin": cross_origin,
        }, separators=(",", ":")).encode()
        auth = hashlib.sha256(rp_id.encode()).digest() + bytes([flags]) + counter.to_bytes(4, "big")
        signature = key.sign(auth + hashlib.sha256(data).digest(), ec.ECDSA(hashes.SHA256()))
        return WebAuthnOwnerAssertion(
            credential_id=b64(credential_id), client_data_json=b64(data),
            authenticator_data=b64(auth), signature=b64(signature),
        )
    return verifier, challenge, create


def test_windows_hello_compatible_passkey_requires_user_verification(owner_auth):
    verifier, challenge, create = owner_auth
    assert verifier.verify(create(counter=7), expected_challenge=challenge, previous_counter=6) == 7
    with pytest.raises(PermissionError):
        verifier.verify(create(flags=1), expected_challenge=challenge, previous_counter=0)
    with pytest.raises(PermissionError):
        verifier.verify(create(flags=4), expected_challenge=challenge, previous_counter=0)
    with pytest.raises(PermissionError):
        verifier.verify(create(counter=5), expected_challenge=challenge, previous_counter=6)


def test_passkey_origin_rp_challenge_and_signature_must_match(owner_auth):
    verifier, challenge, create = owner_auth
    variants = (
        create(origin="http://evil.example"),
        create(cross_origin=True),
        create(rp_id="evil.example"),
        create(issued_challenge=os.urandom(32)),
    )
    for assertion in variants:
        with pytest.raises(PermissionError):
            verifier.verify(assertion, expected_challenge=challenge, previous_counter=0)
    proof = create()
    with pytest.raises(PermissionError):
        verifier.verify(replace(proof, signature=b64(b"bad")),
                        expected_challenge=challenge, previous_counter=0)
    with pytest.raises(ValueError):
        verifier.verify(proof, expected_challenge=b"short", previous_counter=0)


def test_passkey_verifier_rejects_untrusted_credentials_and_origin(owner_auth):
    verifier, challenge, create = owner_auth
    proof = create()
    with pytest.raises(PermissionError):
        verifier.verify(replace(proof, credential_id=b64(os.urandom(32))),
                        expected_challenge=challenge, previous_counter=0)
    with pytest.raises(ValueError):
        OwnerPasskeyVerifier(
            rp_id="127.0.0.1", origin="http://127.0.0.1:5173",
            credential_id=b64(os.urandom(32)),
            public_key_pem=ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
            ),
        )
