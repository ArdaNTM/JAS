"""F2.4 independent AuraAuditor acceptance: only verified broker measurements sign.

Offline tests use a fake IPC transport and throwaway Ed25519 keys. No real
Docker daemon, Windows service or owner private key is read or modified.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aura_core.osworld import audit_broker_attestor as attestor
from aura_core.osworld import audit_broker_client as client
from aura_core.osworld.audit_broker_protocol import BrokerDenied
from aura_core.osworld.audit_broker_receipt import SCHEMA, sign_measurement
from aura_core.osworld.isolation import (
    BootIdentity, IMAGE, EXPECTED_PORTS, REQUIRED_CHECKS,
    verify_receipt, IsolationDenied,
)

RUN = "a" * 32
VM = "b" * 64
NETWORK = "c" * 64
GATEWAY = "d" * 64
INGRESS = "e" * 64
NONCE = "f" * 32
NOW = 1794000000
AUDITOR_SID = "S-1-5-21-111-222-333-1001"
BROKER_SID = "S-1-5-21-111-222-333-1002"
AGENT_SID = "S-1-5-21-111-222-333-1003"
SIGNER_ID = "independent_host"


def public(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def claims(*, nonce: str, vm_sha256: str, checked_at: int = NOW) -> dict:
    return {
        "schema": SCHEMA,
        "run_id": RUN,
        "container_id": VM,
        "nonce": nonce,
        "checked_at": checked_at,
        "boot": {
            "container_id": VM,
            "network_id": NETWORK,
            "vm_sha256": vm_sha256,
            "image": IMAGE,
            "gateway_container_id": GATEWAY,
            "gateway_network_id": INGRESS,
        },
        "checks": {name: True for name in REQUIRED_CHECKS},
        "host_ports": {
            str(p): f"127.0.0.1:{p + 20000}" for p in EXPECTED_PORTS
        },
    }


class FakeBroker:
    def __init__(self, key: Ed25519PrivateKey, vm_sha256: str):
        self.key = key
        self.vm_sha256 = vm_sha256
        self.calls = []
        self.mutate_claims = None
        self.mutate_envelope = None
        self.on_exchange = None
        self.deny = False

    def exchange(self, raw: bytes, *, expected_service_sid: str) -> bytes:
        self.calls.append((raw, expected_service_sid))
        if self.on_exchange is not None:
            self.on_exchange()
        if self.deny:
            return b'{"status":"ISOLATION_BLOCKED","signed":false}'
        req = json.loads(raw)
        obj = claims(nonce=req["nonce"], vm_sha256=self.vm_sha256)
        if self.mutate_claims:
            obj = self.mutate_claims(obj)
        # A service with failed/false checks must not sign anything.
        envelope = sign_measurement(obj, signer=self.key)
        if self.mutate_envelope:
            envelope = self.mutate_envelope(envelope)
        return json.dumps(envelope).encode("utf-8")


class BrokerHostAttestationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vm_image = Path(self.tmp.name) / "System.qcow2"
        self.vm_image.write_bytes(b"independent-osworld-disk-fixture")
        self.image_hash = hashlib.sha256(self.vm_image.read_bytes()).hexdigest()
        self.host_key = Ed25519PrivateKey.generate()
        self.broker_key = Ed25519PrivateKey.generate()
        self.trust = attestor.BrokerTrust(
            AUDITOR_SID, BROKER_SID, public(self.broker_key),
        )
        self.trusted_hosts = {SIGNER_ID: public(self.host_key)}
        self.fake = FakeBroker(self.broker_key, self.image_hash)
        # The Windows hosted runner's tempfile is on C:; the production
        # D: guard remains in place, and is separately tested.
        self.enterContext(patch.object(attestor, "_require_d_disk"))
        self.enterContext(patch.object(
            client, "current_process_sid", return_value=AUDITOR_SID,
        ))
        self.enterContext(patch.object(
            client.time, "time", return_value=NOW,
        ))

    def attest(self, **changes):
        params = {
            "run_id": RUN,
            "container_id": VM,
            "vm_image": self.vm_image,
            "trust": self.trust,
            "signer_id": SIGNER_ID,
            "signer": self.host_key,
            "trusted_public_keys": self.trusted_hosts,
            "transport": self.fake,
        }
        params.update(changes)
        return attestor.attest_via_broker(**params)

    def test_valid_broker_measurement_becomes_host_signed_receipt(self):
        receipt = self.attest()
        self.assertEqual(receipt.boot.vm_sha256, self.image_hash)
        self.assertEqual(receipt.boot.container_id, VM)
        self.assertEqual(receipt.checked_at, NOW)
        self.assertEqual(receipt.expires_at, NOW + 180)
        self.assertTrue(all(receipt.checks.values()))
        request = json.loads(self.fake.calls[0][0])
        self.assertEqual(receipt.nonce, request["nonce"])
        self.assertEqual(self.fake.calls[0][1], BROKER_SID)
        verify_receipt(
            receipt, expected=receipt.boot,
            trusted_public_keys=self.trusted_hosts, now=NOW,
        )

    def test_broker_denial_never_produces_host_receipt(self):
        self.fake.deny = True
        with self.assertRaises(BrokerDenied):
            self.attest()

    def test_broker_signature_tampering_never_produces_host_receipt(self):
        def tamper(env):
            return {**env, "host_ports": {
                **env["host_ports"], "5000": "127.0.0.1:65000",
            }}
        self.fake.mutate_envelope = tamper
        with self.assertRaises(BrokerDenied):
            self.attest()

    def test_untrusted_broker_public_key_never_signs(self):
        self.trust = attestor.BrokerTrust(
            AUDITOR_SID, BROKER_SID, public(Ed25519PrivateKey.generate())
        )
        with self.assertRaises(BrokerDenied):
            self.attest()

    def test_fake_positive_claim_with_false_probe_cannot_sign(self):
        def negative(data):
            data["checks"]["metadata_blocked"] = False
            return data
        self.fake.mutate_claims = negative
        with self.assertRaises(BrokerDenied):
            self.attest()

    def test_broker_measurement_bound_to_run_id(self):
        with self.assertRaises(BrokerDenied):
            self.attest(run_id="f" * 32)

    def test_broker_measurement_bound_to_container_id(self):
        with self.assertRaises(BrokerDenied):
            self.attest(container_id="f" * 64)

    def test_measured_disk_hash_mismatch_denied(self):
        self.fake.vm_sha256 = "f" * 64
        with self.assertRaises(BrokerDenied):
            self.attest()

    def test_disk_mutation_during_ipc_denied(self):
        self.fake.on_exchange = lambda: self.vm_image.write_bytes(b"mutated")
        with self.assertRaises(BrokerDenied):
            self.attest()

    def test_same_signing_key_for_broker_and_host_rejected(self):
        self.trust = attestor.BrokerTrust(
            AUDITOR_SID, BROKER_SID, public(self.host_key),
        )
        with self.assertRaises(BrokerDenied):
            self.attest()
        self.assertEqual(self.fake.calls, [])

    def test_host_signer_key_must_be_independently_pinned(self):
        with self.assertRaises(BrokerDenied):
            self.attest(trusted_public_keys={
                SIGNER_ID: public(Ed25519PrivateKey.generate()),
            })
        self.assertEqual(self.fake.calls, [])

    def test_wrong_auditor_sid_denied_before_exchange(self):
        with patch.object(client, "current_process_sid", return_value=AGENT_SID):
            with self.assertRaises(BrokerDenied):
                self.attest()
        self.assertEqual(self.fake.calls, [])

    def test_expired_broker_claim_cannot_sign(self):
        self.fake.mutate_claims = lambda c: {**c, "checked_at": NOW - 31}
        with self.assertRaises(BrokerDenied):
            self.attest()

    def test_invalid_partial_receipt_claim_rejected(self):
        self.fake.mutate_claims = lambda c: {**c, "checks": {}}
        with self.assertRaises(BrokerDenied):
            self.attest()

    def test_symlinked_qcow2_cannot_be_authenticated(self):
        link = Path(self.tmp.name) / "alias.qcow2"
        try:
            link.symlink_to(self.vm_image)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink unavailable in this environment")
        with self.assertRaises(BrokerDenied):
            self.attest(vm_image=link)
        self.assertEqual(self.fake.calls, [])


class ProtectedBrokerTrustTests(unittest.TestCase):
    def test_strict_trust_policy_parses(self):
        policy = {
            "schema": attestor.TRUST_SCHEMA,
            "auditor_sid": AUDITOR_SID,
            "broker_service_sid": BROKER_SID,
            "broker_public_key_hex": "f" * 64,
        }
        p = attestor.parse_broker_trust(json.dumps(policy).encode())
        self.assertEqual(p.auditor_sid, AUDITOR_SID)
        self.assertEqual(p.broker_service_sid, BROKER_SID)
        self.assertEqual(p.public_key, bytes.fromhex("f" * 64))

    def test_same_or_untrusted_identity_rejected(self):
        base = {
            "schema": attestor.TRUST_SCHEMA,
            "auditor_sid": AUDITOR_SID,
            "broker_service_sid": BROKER_SID,
            "broker_public_key_hex": "f" * 64,
        }
        for broker_sid in (AUDITOR_SID, AGENT_SID + ";", "S-1-5-18", ""):
            with self.subTest(sid=broker_sid):
                with self.assertRaises(BrokerDenied):
                    attestor.parse_broker_trust(json.dumps({
                        **base, "broker_service_sid": broker_sid,
                    }).encode())

    def test_duplicate_json_key_denied(self):
        raw = (
            '{"schema":"aura.osworld.broker-trust.v1",'
            '"auditor_sid":"' + AUDITOR_SID + '",'
            '"auditor_sid":"' + AUDITOR_SID + '",'
            '"broker_service_sid":"' + BROKER_SID + '",'
            '"broker_public_key_hex":"' + "f" * 64 + '"}'
        ).encode()
        with self.assertRaises(BrokerDenied):
            attestor.parse_broker_trust(raw)

    def test_invalid_public_key_and_unknown_policy_rejected(self):
        valid = {
            "schema": attestor.TRUST_SCHEMA,
            "auditor_sid": AUDITOR_SID,
            "broker_service_sid": BROKER_SID,
            "broker_public_key_hex": "f" * 64,
        }
        for edits in (
            {"broker_public_key_hex": "abc"},
            {"broker_public_key_hex": "X" * 64},
            {"schema": "legacy"},
            {"docker_host": "tcp://evil:2375"},
        ):
            with self.subTest(edits=edits), self.assertRaises(BrokerDenied):
                attestor.parse_broker_trust(json.dumps({
                    **valid, **edits,
                }).encode())

    def test_file_inside_mutable_checkout_denied(self):
        with self.assertRaises(BrokerDenied):
            attestor._protected_operator_file(
                Path(attestor.__file__).resolve()
            )

    def test_trust_file_exclusive_path_policy(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            filename = base / "trust.json"
            filename.write_text("{}", encoding="utf-8")
            filename.chmod(0o600)
            if os.name != "nt":
                # Linux temp directories created by tempfile are mode 0700.
                attestor._protected_operator_file(filename)
            filename.chmod(0o666)
            if os.name != "nt":
                with self.assertRaises(BrokerDenied):
                    attestor._protected_operator_file(filename)

    def test_trust_file_symlink_denied(self):
        with TemporaryDirectory() as directory:
            file = Path(directory) / "key.json"
            file.write_text("{}", encoding="utf-8")
            link = Path(directory) / "alias.json"
            try:
                link.symlink_to(file)
            except (OSError, NotImplementedError):
                self.skipTest("Symlink unavailable")
            with self.assertRaises(BrokerDenied):
                attestor._protected_operator_file(link)


class AttestorCommandContractTests(unittest.TestCase):
    def test_no_direct_docker_fallback(self):
        path = Path(__file__).resolve().parents[1] / "scripts" / "attest_osworld_network.py"
        content = path.read_text(encoding="utf-8")
        self.assertNotIn("from aura_core.osworld.network_audit import audit_network", content)
        self.assertNotIn("audit_network(", content)
        self.assertIn("--broker-trust", content)
        self.assertIn("attest_via_broker(", content)

    def test_missing_broker_never_generates_receipt_file(self):
        path = Path(__file__).resolve().parents[1] / "scripts" / "attest_osworld_network.py"
        spec = importlib.util.spec_from_file_location("test_f24_auditor_cli", path)
        self.assertIsNotNone(spec)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with TemporaryDirectory() as directory:
            output = Path(directory) / "signed.json"
            args = [
                "--run-id", RUN, "--container", VM,
                "--vm-image", str(Path(directory) / "disk.qcow2"),
                "--broker-trust", str(Path(directory) / "trust.json"),
                "--signer-id", SIGNER_ID,
                "--private-key", str(Path(directory) / "host.pem"),
                "--trusted-public-keys", str(Path(directory) / "hosts.json"),
                "--out", str(output),
            ]
            captured = io.StringIO()
            with (
                patch.object(mod, "load_broker_trust",
                             return_value=attestor.BrokerTrust(
                                 AUDITOR_SID, BROKER_SID,
                                 public(Ed25519PrivateKey.generate()),
                             )),
                patch.object(mod, "_protected_private_key",
                             return_value=Ed25519PrivateKey.generate()),
                patch.object(mod, "_protected_operator_file"),
                patch.object(mod, "load_pinned_public_keys", return_value={}),
                patch.object(mod, "attest_via_broker",
                             side_effect=BrokerDenied("Broker not enabled")),
                contextlib.redirect_stdout(captured),
            ):
                self.assertEqual(mod.main(args), 2)
            self.assertFalse(output.exists())
            reported = json.loads(captured.getvalue())
            self.assertEqual(reported["status"], "ISOLATION_BLOCKED")
            self.assertIs(reported["signed"], False)


if __name__ == "__main__":
    unittest.main()
