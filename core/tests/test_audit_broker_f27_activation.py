"""F2.7 independent approval: real ephemeral Ed25519, strict binding and isolation tests."""
from __future__ import annotations

import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from aura_core.osworld.audit_broker_protocol import BrokerDenied
from aura_core.osworld import audit_broker_f27_activation as activation

NOW = 1794000000
SERVICE = "S-1-5-21-1-2-3-1002"
AUDITOR = "S-1-5-21-1-2-3-1001"
AGENT = "S-1-5-21-1-2-3-1003"


class OperatorApprovalTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.pub = self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.policy = json.dumps({
            "schema": "aura.osworld.broker-service.v1",
            "service_sid": SERVICE, "auditor_sid": AUDITOR,
            "agent_sid": AGENT, "mode": "audit_only",
        }, sort_keys=True).encode()
        self.inventory = b'{"schema":"aura.osworld.f27-runtime-inventory.v1","files":[]}'
        self.hosts = b'192.168.247.2 ssh-ed25519 AAAA'
        self.claims = {
            "mode": "audit_only", "service_sid": SERVICE, "auditor_sid": AUDITOR,
            "agent_sid": AGENT, "run_id": "a"*32, "vm_id": "b"*64,
            "vm_disk_sha256": "c"*64,
            "policy_sha256": activation._sha(self.policy),
            "runtime_inventory_sha256": activation._sha(self.inventory),
            "known_hosts_sha256": activation._sha(self.hosts),
            "approval_nonce": "d"*32, "issued_at": NOW, "expires_at": NOW+300,
        }

    def envelope(self, claims=None, *, signer=None):
        signed = self.claims if claims is None else claims
        signature = (self.key if signer is None else signer).sign(
            activation.signed_approval_bytes(signed)
        )
        return json.dumps({
            "schema": activation.APPROVAL_SCHEMA, "claims": signed,
            "signature_b64": base64.b64encode(signature).decode("ascii"),
        }, sort_keys=True).encode("ascii")

    def check(self, envelope=None, *, policy=None, inventory=None, hosts=None, epoch=NOW):
        return activation.verify_operator_approval(
            self.envelope() if envelope is None else envelope,
            self.pub, policy_raw=self.policy if policy is None else policy,
            runtime_inventory_raw=self.inventory if inventory is None else inventory,
            known_hosts_raw=self.hosts if hosts is None else hosts,
            now=epoch,
        )

    def test_valid_expiring_operator_signature_and_exact_identities(self):
        result = self.check()
        self.assertEqual(result.policy.service_sid, SERVICE)
        self.assertEqual(result.policy.mode, "audit_only")
        self.assertEqual(result.vm_disk_sha256, "c"*64)
        self.assertEqual(result.expires_at, NOW+300)

    def test_wrong_signer_and_tampered_envelope_rejected(self):
        untrusted = Ed25519PrivateKey.generate()
        with self.assertRaises(BrokerDenied):
            self.check(self.envelope(signer=untrusted))
        data = json.loads(self.envelope())
        data["claims"]["service_sid"] = AGENT
        with self.assertRaises(BrokerDenied):
            self.check(json.dumps(data).encode())

    def test_wrong_policy_runtime_host_or_source_identity_denied(self):
        for arg in (
            {"policy": self.policy + b" "},
            {"inventory": self.inventory + b" "},
            {"hosts": self.hosts + b" "},
            {"policy": self.policy.replace(b'"audit_only"', b'"deny_only"')},
        ):
            with self.subTest(arg=arg.keys()), self.assertRaises(BrokerDenied):
                self.check(**arg)

    def test_expired_and_overlong_policy_denied(self):
        with self.assertRaises(BrokerDenied):
            self.check(epoch=NOW+300)
        long_claim = dict(self.claims, expires_at=NOW+901)
        with self.assertRaises(BrokerDenied):
            self.check(self.envelope(long_claim))
        backdated = dict(self.claims, issued_at=NOW-65)
        with self.assertRaises(BrokerDenied):
            self.check(self.envelope(backdated))

    def test_duplicate_json_and_extra_fields_denied(self):
        raw = self.envelope()
        with self.assertRaises(BrokerDenied):
            self.check(raw[:-1] + b', "schema":"duplicate"}')
        extra = dict(self.claims, arbitrary_docker_args="--privileged")
        with self.assertRaises(BrokerDenied):
            self.check(self.envelope(extra))

    def test_public_deny_only_parser_still_rejects_audit_only(self):
        from aura_core.osworld.audit_broker_service import parse_service_policy
        with self.assertRaises(BrokerDenied):
            parse_service_policy(self.policy)


class RuntimeManifestTests(unittest.TestCase):
    def test_exact_bounded_sha_inventory_and_extra_file_detection(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "python.exe").write_bytes(b"test runtime")
            entry = {"path": "python.exe", "sha256": activation._sha(b"test runtime")}
            raw = json.dumps({
                "schema": activation.INVENTORY_SCHEMA,
                "files": [entry],
            }).encode()
            activation.verify_exact_runtime_inventory(raw, root=root)
            (root / "outside.py").write_bytes(b"mutated")
            with self.assertRaises(BrokerDenied):
                activation.verify_exact_runtime_inventory(raw, root=root)
            (root / "outside.py").unlink()
            (root / "python.exe").write_bytes(b"tampered")
            with self.assertRaises(BrokerDenied):
                activation.verify_exact_runtime_inventory(raw, root=root)

    def test_manifest_traversal_and_bad_hash_fail_closed(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for entry in [
                {"path": "../escape", "sha256": "a"*64},
                {"path": "evil:ads", "sha256": "a"*64},
                {"path": "ok.bin", "sha256": "a"*62},
            ]:
                with self.subTest(entry=entry), self.assertRaises(BrokerDenied):
                    raw = json.dumps({
                        "schema": activation.INVENTORY_SCHEMA,
                        "files": [entry],
                    }).encode()
                    activation.verify_exact_runtime_inventory(raw, root=root)
