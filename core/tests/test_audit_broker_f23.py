"""F2.3 security tests: immutable image, deterministic probes and topology contracts."""
from __future__ import annotations

import errno
import json
import os
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aura_core.osworld.audit_broker_protocol import BrokerDenied
from aura_core.osworld import audit_broker_docker as docker

VM = "a" * 64
RUN = "b" * 32


class FakeEngine:
    def __init__(self):
        self.calls = []
        self.result = {
            "schema": docker.PROBE_SCHEMA,
            "name": "egress_v4_blocked",
            "errno": errno.ENETUNREACH,
            "blocked": True,
        }
        self.rc = 0
        self.out = None

    def __call__(self, command, **kw):
        self.calls.append((command, kw))
        if "run" in command:
            expected = json.loads(command[-1])["name"]
            response = dict(self.result, name=expected)
            return SimpleNamespace(
                returncode=self.rc,
                stdout=self.out if self.out is not None else json.dumps(response),
                stderr="",
            )
        return SimpleNamespace(returncode=self.rc, stdout="[]", stderr="")


class DockerF23PolicyTests(unittest.TestCase):
    def setUp(self):
        self.runner = FakeEngine()
        self.backend = docker.DockerAuditBackend(runner=self.runner)

    def test_existing_repository_image_is_immutable_digest(self):
        self.assertEqual(docker.PROBE_IMAGE, docker.network_audit.GATEWAY_IMAGE)
        self.assertIn("@sha256:", docker.PROBE_IMAGE)
        self.assertRegex(docker.PROBE_IMAGE, r"@sha256:[0-9a-f]{64}$")

    def test_floating_image_is_rejected_before_daemon(self):
        with patch.object(docker, "PROBE_IMAGE", "alpine:3.21"):
            with self.assertRaises(BrokerDenied):
                docker.DockerAuditBackend(runner=self.runner)
        self.assertEqual(self.runner.calls, [])

    def test_bounded_docker_cli_is_pinned_to_service_config(self):
        self.backend.inspect_container(VM)
        argv, kw = self.runner.calls[0]
        self.assertEqual(argv[:5], [
            str(docker.DOCKER_EXE), "--config", str(docker.DOCKER_CONFIG),
            "--context", docker.DOCKER_CONTEXT,
        ])
        self.assertEqual(argv[-2:], ["inspect", VM])
        self.assertFalse(kw["shell"])
        self.assertEqual(kw["timeout"], docker.READ_TIMEOUT)

    def test_hostile_docker_environment_is_not_inherited(self):
        with patch.dict(os.environ, {
            "DOCKER_HOST": "tcp://evil:2375",
            "DOCKER_TLS_VERIFY": "0",
            "DOCKER_CONTEXT": "evil",
        }):
            self.backend.inspect_container(VM)
        env = self.runner.calls[0][1]["env"]
        for bad in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY"):
            self.assertNotIn(bad, env)

    def test_probes_no_mounts_privilege_or_mutable_images(self):
        self.assertTrue(self.backend.fixed_probe(container_id=VM, name="egress_v4_blocked"))
        argv, kw = self.runner.calls[-1]
        self.assertIn("run", argv)
        for value in ("--read-only", "--cap-drop", "--user", "--pull", "never",
                      "--security-opt", "no-new-privileges"):
            self.assertIn(value, argv)
        self.assertNotIn("--privileged", argv)
        self.assertNotIn("--mount", argv)
        self.assertNotIn("--volume", argv)
        self.assertEqual(argv[argv.index("--network") + 1], "container:" + VM)
        self.assertEqual(argv[argv.index("--entrypoint") + 1], "python3")
        self.assertIn(docker.PROBE_IMAGE, argv)
        self.assertFalse(kw["shell"])

    def test_successful_tcp_connection_is_not_blocked(self):
        self.runner.result["errno"] = 0
        self.runner.result["blocked"] = False
        self.assertFalse(self.backend.fixed_probe(container_id=VM, name="egress_v4_blocked"))

    def test_connection_refused_is_not_proof_of_isolation(self):
        self.runner.result["errno"] = errno.ECONNREFUSED
        self.runner.result["blocked"] = False
        self.assertFalse(self.backend.fixed_probe(container_id=VM, name="metadata_blocked"))

    def test_timeout_is_not_proof_of_isolation(self):
        self.runner.result["errno"] = errno.ETIMEDOUT
        self.runner.result["blocked"] = False
        self.assertFalse(self.backend.fixed_probe(container_id=VM, name="metadata_blocked"))

    def test_missing_probe_interpreter_is_not_proof(self):
        self.runner.rc = 127
        self.assertFalse(self.backend.fixed_probe(container_id=VM, name="ipv6_blocked"))

    def test_probe_forged_boolean_or_wrong_type_rejected(self):
        self.runner.result["blocked"] = 1
        self.assertFalse(self.backend.fixed_probe(container_id=VM, name="egress_v4_blocked"))
        self.runner.result["blocked"] = True
        self.runner.result["errno"] = "101"
        self.assertFalse(self.backend.fixed_probe(container_id=VM, name="egress_v4_blocked"))

    def test_probe_mismatched_or_extra_fields_rejected(self):
        self.runner.result["schema"] = "other"
        self.assertFalse(self.backend.fixed_probe(container_id=VM, name="egress_v4_blocked"))
        self.runner.result["schema"] = docker.PROBE_SCHEMA
        self.runner.result["new-field"] = "untrusted"
        self.assertFalse(self.backend.fixed_probe(container_id=VM, name="egress_v4_blocked"))

    def test_probe_non_json_stdout_rejected(self):
        self.runner.out = "AURA_DENIED"
        self.assertFalse(self.backend.fixed_probe(container_id=VM, name="metadata_blocked"))

    def test_probe_oversized_stdout_rejected(self):
        self.runner.out = "x" * (docker.MAX_PROBE_OUTPUT + 1)
        self.assertFalse(self.backend.fixed_probe(container_id=VM, name="ipv6_blocked"))

    def test_arbitrary_network_or_volume_inspect_rejected(self):
        for args in (["network", "inspect", "bridge"],
                     ["volume", "inspect", "host-secrets"],
                     ["run", "--privileged"],
                     ["inspect", "not-a-full-id"]):
            with self.subTest(args=args), self.assertRaises(BrokerDenied):
                self.backend.policy_inspect(args)
        self.assertEqual(self.runner.calls, [])

    def test_exact_inspect_allowlist(self):
        self.backend.policy_inspect(["inspect", VM])
        self.backend.policy_inspect(["inspect", docker.network_audit.GATEWAY_PREFIX + RUN])
        self.backend.policy_inspect(["network", "inspect", docker.network_audit.NETWORK_NAME])
        self.backend.policy_inspect(["network", "inspect", docker.network_audit.INGRESS_PREFIX + RUN])
        self.backend.policy_inspect(["volume", "inspect", docker.network_audit.STORAGE_VOLUME_PREFIX + RUN])
        self.assertEqual(len(self.runner.calls), 5)

    def test_host_gateway_rejects_public_address(self):
        with self.assertRaises(BrokerDenied):
            self.backend.fixed_probe(container_id=VM, name="host_gateway_blocked", gateway_ip="1.1.1.1")
        self.assertEqual(self.runner.calls, [])

    def test_all_gateway_ports_must_be_denied(self):
        self.assertTrue(self.backend.fixed_probe(
            container_id=VM, name="host_gateway_blocked", gateway_ip="172.25.0.1"
        ))
        self.assertEqual(len(self.runner.calls), len(docker.GATEWAY_PORTS))
        ports = [json.loads(call[0][-1])["port"] for call in self.runner.calls]
        self.assertEqual(tuple(ports), docker.GATEWAY_PORTS)

    def test_gateway_probe_rejects_one_reachable_port(self):
        class OneOpen(FakeEngine):
            def __call__(self, command, **kw):
                result = super().__call__(command, **kw)
                if "run" in command and json.loads(command[-1])["port"] == 443:
                    d = json.loads(result.stdout)
                    d["errno"] = 0
                    d["blocked"] = False
                    result.stdout = json.dumps(d)
                return result
        self.assertFalse(docker.DockerAuditBackend(runner=OneOpen()).fixed_probe(
            container_id=VM, name="host_gateway_blocked", gateway_ip="172.25.0.1",
        ))

    def test_non_allowlisted_probe_is_denied_before_daemon(self):
        with self.assertRaises(BrokerDenied):
            self.backend.fixed_probe(container_id=VM, name="shell", gateway_ip=None)
        self.assertEqual(self.runner.calls, [])



# Reuse the production topology acceptance fixtures rather than substituting
# a smaller broker-specific topology policy.
from test_osworld_secure_live import _docker_inspection, _fake_docker_json
from aura_core.osworld.audit_broker_protocol import AuditRequest
from aura_core.osworld.audit_broker_topology import BrokerTopologyAudit
from aura_core.osworld.isolation import IsolationDenied, REQUIRED_CHECKS
from tempfile import TemporaryDirectory


class TopologyRunner(FakeEngine):
    def __init__(self):
        super().__init__()
        self.vm, self.network = _docker_inspection()
        self.fail_probe = None

    def __call__(self, command, **kw):
        self.calls.append((command, kw))
        args = command[5:]
        if args[0] == "run":
            req = json.loads(args[-1])
            rc = 0 if req["name"] != self.fail_probe else errno.ETIMEDOUT
            out = json.dumps({
                "schema": docker.PROBE_SCHEMA,
                "name": req["name"],
                "errno": errno.ENETUNREACH if rc == 0 else rc,
                "blocked": rc == 0,
            })
            return SimpleNamespace(returncode=0, stdout=out, stderr="")
        return SimpleNamespace(returncode=0, stdout=json.dumps(
            _fake_docker_json(args, self.vm, self.network)
        ), stderr="")


class BrokerTopologyF23Tests(unittest.TestCase):
    def setUp(self):
        # Hosted Windows uses C: temporary directories; production's D:
        # enforcement is tested separately and remains enabled in real code.
        self.enterContext(patch(
            "aura_core.osworld.audit_broker_topology._require_d_drive"
        ))
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.image = Path(self.temp.name) / "System.qcow2"
        self.image.write_bytes(b"trusted-pinned-osworld-disk-fixture")
        self.runner = TopologyRunner()
        self.backend = docker.DockerAuditBackend(runner=self.runner)
        self.audit = BrokerTopologyAudit(
            backend=self.backend, pinned_vm_image=self.image
        )
        self.req = AuditRequest("f" * 32, VM, "c" * 32, 1794000000)

    def test_original_topology_policy_retained_with_broker_io(self):
        boot, ports, checks = self.audit.audit(self.req)
        self.assertEqual(boot.container_id, VM)
        self.assertEqual(set(checks), REQUIRED_CHECKS)
        self.assertTrue(all(checks.values()))
        self.assertIn("5000", ports)
        inspected = [call[0][5:] for call in self.runner.calls
                     if "inspect" in call[0]]
        self.assertIn(["inspect", VM], inspected)
        self.assertIn(["network", "inspect", docker.network_audit.NETWORK_NAME], inspected)
        self.assertIn(["volume", "inspect", docker.network_audit.STORAGE_VOLUME_PREFIX + "f" * 32], inspected)

    def test_request_run_id_must_match_inspected_label(self):
        self.req = AuditRequest("e" * 32, VM, "c" * 32, 1794000000)
        with self.assertRaises(BrokerDenied):
            self.audit.audit(self.req)
        self.assertFalse(any("run" in call[0] for call in self.runner.calls))

    def test_privileged_vm_rejected_by_existing_policy(self):
        self.runner.vm["HostConfig"]["Privileged"] = True
        with self.assertRaises(IsolationDenied):
            self.audit.audit(self.req)

    def test_probe_ambiguity_denies_full_topology_attestation(self):
        self.runner.fail_probe = "metadata_blocked"
        with self.assertRaises(IsolationDenied):
            self.audit.audit(self.req)

    def test_mutated_container_id_is_rejected(self):
        self.runner.vm["Id"] = "e" * 64
        with self.assertRaises(BrokerDenied):
            self.audit.audit(self.req)

    def test_symlinked_disk_is_not_trusted(self):
        other = Path(self.temp.name) / "linked.qcow2"
        try:
            other.symlink_to(self.image)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation unavailable")
        with self.assertRaises(BrokerDenied):
            BrokerTopologyAudit(backend=self.backend, pinned_vm_image=other)



from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from aura_core.osworld.audit_broker_measurement import evaluate_broker_measurement
from aura_core.osworld.audit_broker_receipt import verify_measurement
from aura_core.osworld.audit_broker_protocol import PROTOCOL, OPERATION

AUDITOR_SID = "S-1-5-21-111-222-333-1001"
AGENT_SID = "S-1-5-21-111-222-333-1003"
FIXED_NOW = 1794000000


class BrokerMeasuredReceiptF23Tests(BrokerTopologyF23Tests):
    def setUp(self):
        super().setUp()
        self.signer = Ed25519PrivateKey.generate()
        self.used = set()

    def claim_nonce(self, nonce):
        if nonce in self.used:
            return False
        self.used.add(nonce)
        return True

    def message(self, **overrides):
        data = {
            "protocol": PROTOCOL, "operation": OPERATION,
            "run_id": "f" * 32, "container_id": VM,
            "nonce": "c" * 32, "issued_at": FIXED_NOW,
        }
        data.update(overrides)
        return json.dumps(data).encode("utf-8")

    def measure(self, raw=None, **overrides):
        args = {
            "peer_sid": AUDITOR_SID,
            "auditor_sid": AUDITOR_SID,
            "topology": self.audit,
            "claim_nonce": self.claim_nonce,
            "signer": self.signer,
            "now": FIXED_NOW,
        }
        args.update(overrides)
        return evaluate_broker_measurement(self.message() if raw is None else raw, **args)

    def test_complete_broker_audit_generates_verifiable_measurement(self):
        wire = self.measure()
        envelope = json.loads(wire)
        public = self.signer.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        validated = verify_measurement(
            envelope, pinned_public_key=public,
            expected_run_id="f" * 32, expected_container_id=VM,
            expected_nonce="c" * 32, now=FIXED_NOW,
        )
        self.assertEqual(validated["boot"]["container_id"], VM)
        self.assertEqual(set(validated["checks"]), REQUIRED_CHECKS)
        self.assertTrue(all(validated["checks"].values()))

    def test_replayed_nonce_denied_before_second_probe(self):
        message = self.message()
        self.measure(message)
        count = len(self.runner.calls)
        with self.assertRaises(BrokerDenied):
            self.measure(message)
        self.assertLessEqual(len(self.runner.calls), count + 1)

    def test_untrusted_caller_rejected_before_docker_inspection(self):
        with self.assertRaises(BrokerDenied):
            self.measure(peer_sid=AGENT_SID)
        self.assertEqual(self.runner.calls, [])

    def test_wrong_run_ownership_fails_without_consuming_nonce(self):
        with self.assertRaises(BrokerDenied):
            self.measure(self.message(run_id="e" * 32))
        self.assertEqual(self.used, set())

    def test_arbitrary_operation_denied_before_docker(self):
        with self.assertRaises(BrokerDenied):
            self.measure(self.message(operation="docker exec"))
        self.assertEqual(self.runner.calls, [])

    def test_uncertain_network_result_cannot_be_signed(self):
        self.runner.fail_probe = "metadata_blocked"
        with self.assertRaises(IsolationDenied):
            self.measure()
        self.assertIn("c" * 32, self.used)

    def test_untrusted_or_missing_signer_denied(self):
        with self.assertRaises(BrokerDenied):
            self.measure(signer=None)
        self.assertEqual(self.runner.calls, [])

    def test_output_cannot_be_verified_using_an_unpinned_broker_key(self):
        wire = self.measure()
        invalid_public = Ed25519PrivateKey.generate().public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        with self.assertRaises(BrokerDenied):
            verify_measurement(
                json.loads(wire), pinned_public_key=invalid_public,
                expected_run_id="f" * 32, expected_container_id=VM,
                expected_nonce="c" * 32, now=FIXED_NOW,
            )

    def test_signer_receipt_is_not_aura_host_isolation_receipt(self):
        wire = self.measure()
        data = json.loads(wire)
        self.assertEqual(data["schema"], "aura.osworld.docker-broker-measurement.v1")
        self.assertNotIn("ISOLATION_SIGNED", wire.decode())
        self.assertNotIn("signer_id", data)


if __name__ == "__main__":
    unittest.main()
