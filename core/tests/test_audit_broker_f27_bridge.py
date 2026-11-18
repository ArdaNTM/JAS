"""F2.7 isolated Windows request gate, durable replay and unsigned audit tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from aura_core.osworld.audit_broker_protocol import BrokerDenied
from aura_core.osworld.audit_broker_service import BrokerServicePolicy
from aura_core.osworld.audit_broker_f27_activation import ApprovedActivation
from aura_core.osworld import audit_broker_f27_bridge as bridge
from aura_core.osworld import network_audit

RUN = "a" * 32
VM = "b" * 64
NONCE = "c" * 32
AUDITOR = "S-1-5-21-1-2-3-1001"
SERVICE = "S-1-5-21-1-2-3-1002"
AGENT = "S-1-5-21-1-2-3-1003"
NOW = 1794000000


def make_request(*, nonce=NONCE, run=RUN, vm=VM, issued=NOW):
    return json.dumps({
        "protocol": "aura.docker-audit.request.v1",
        "operation": "audit_osworld_network",
        "run_id": run, "container_id": vm, "nonce": nonce, "issued_at": issued,
    }).encode("ascii")


def approved():
    return ApprovedActivation(
        policy=BrokerServicePolicy(SERVICE, AUDITOR, AGENT, "audit_only"),
        run_id=RUN, vm_id=VM, vm_disk_sha256="d"*64,
        nonce="e"*32, expires_at=NOW+100,
    )


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "nonces.db"
        self.store = bridge.DurableWindowsNonceStore(self.db, enforce_host=False)

    def test_persistent_nonce_across_process_reopen(self):
        self.assertTrue(self.store.claim(NONCE, kind="request"))
        self.assertFalse(bridge.DurableWindowsNonceStore(self.db, enforce_host=False).claim(NONCE, kind="request"))
        self.assertFalse(self.store.claim(NONCE, kind="operator"))

    def test_atomic_one_winner(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            wins = list(pool.map(lambda _: self.store.claim(NONCE, kind="request"), range(10)))
        self.assertEqual(wins.count(True), 1)

    def test_malformed_nonce_and_kind_denied(self):
        for nonce, kind in (("../evil", "request"), (NONCE, "write"), ("A"*32, "request")):
            with self.subTest(nonce=nonce, kind=kind), self.assertRaises(BrokerDenied):
                self.store.claim(nonce, kind=kind)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.claim = Mock(return_value=True)
        self.trans = Mock()
        self.backend = Mock()
        self.gateway = "f" * 64
        self.backend.policy_inspect.return_value = [{
            "IPAM": {"Config": [{"Gateway": "172.19.0.1"}]}
        }]
        self.backend.fixed_probe.return_value = True
        self.disk_proof = {
            "schema": "aura.osworld.vm-disk-measurement.v1",
            "run_id": RUN, "vm_id": VM, "sha256": "d"*64,
            "bytes": 8192, "source": "/var/lib/aura-images/osworld-v2-ubuntu-x86.qcow2",
            "dev": 1, "ino": 2,
        }
        self.backend.measure_disk.return_value = dict(self.disk_proof)
        self.factory = Mock(return_value=self.backend)

    def call(self, raw=None, sid=AUDITOR, activation=None, epoch=NOW):
        with patch.object(network_audit, "inspect_topology", return_value=(
                type("Boot", (), {"gateway_container_id": self.gateway})(),
                {"5000": "localhost"}, "172.17.0.1",
            )), patch.object(network_audit, "negative_network_probes", return_value={
                "egress_v4_blocked": True,
                "metadata_blocked": True,
                "external_dns_blocked": True,
                "ipv6_blocked": True,
                "host_gateway_blocked": True,
            }):
            return bridge.inspect_approved_run(
                make_request() if raw is None else raw, sid,
                approved() if activation is None else activation,
                claim_nonce=self.claim,
                backend_factory=self.factory,
                transport_factory=lambda: self.trans,
                now=epoch,
            )

    def test_only_unsigned_observation_with_all_checks(self):
        body = self.call()
        result = json.loads(body)
        self.assertEqual(result["status"], "AUDIT_OBSERVED_UNSIGNED")
        self.assertIs(result["signed"], False)
        self.assertNotIn(b"ISOLATION_SIGNED", body)
        self.claim.assert_called_once_with(NONCE)
        self.factory.assert_called_once_with(transport=self.trans, run_id=RUN, vm_id=VM)
        self.assertEqual(self.backend.measure_disk.call_count, 2)

    def test_root_measurement_must_match_signed_vm_disk(self):
        for forged in (
            dict(self.disk_proof, sha256="f"*64),
            dict(self.disk_proof, run_id="f"*32),
            dict(self.disk_proof, vm_id="f"*64),
            dict(self.disk_proof, source="C:/malicious"),
            None,
        ):
            self.backend.measure_disk.return_value = forged
            with self.subTest(proof=forged), self.assertRaises(BrokerDenied):
                self.call()
        self.backend.policy_inspect.assert_not_called()

    def test_post_measurement_rejects_swapped_disk_and_mutation(self):
        for changed in (
            dict(self.disk_proof, sha256="f"*64),
            dict(self.disk_proof, source="/var/lib/aura-images/other.qcow2"),
            dict(self.disk_proof, ino=91),
            dict(self.disk_proof, bytes=8193),
        ):
            self.backend.measure_disk.side_effect = [dict(self.disk_proof), changed]
            with self.subTest(post=changed), self.assertRaises(BrokerDenied):
                self.call()
            self.backend.measure_disk.reset_mock(side_effect=True)

    def test_wrong_agent_or_vm_never_claims_nonce_or_uses_ssh(self):
        for raw, sid in [
            (make_request(), AGENT),
            (make_request(run="f"*32), AUDITOR),
            (make_request(vm="a"*64), AUDITOR),
            (make_request(issued=NOW-60), AUDITOR),
        ]:
            with self.subTest(sid=sid), self.assertRaises(BrokerDenied):
                self.call(raw=raw, sid=sid)
        self.claim.assert_not_called()
        self.factory.assert_not_called()

    def test_replayed_nonce_never_uses_transport(self):
        self.claim.return_value = False
        with self.assertRaises(BrokerDenied):
            self.call()
        self.factory.assert_not_called()

    def test_expired_operator_approval_never_uses_transport(self):
        with self.assertRaises(BrokerDenied):
            self.call(epoch=NOW+100)
        self.claim.assert_not_called()
        self.factory.assert_not_called()

    def test_backend_error_never_issues_unsigned_success(self):
        self.backend.policy_inspect.side_effect = BrokerDenied("remote helper refused")
        with self.assertRaises(BrokerDenied):
            self.call()

    def test_handler_never_installs_scm_or_signs(self):
        from pathlib import Path
        source = Path(bridge.__file__).read_text("utf-8")
        self.assertNotIn('"status": "ISOLATION_SIGNED"', source)
        self.assertNotIn("CreateService(", source)
