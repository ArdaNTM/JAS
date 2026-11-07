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


if __name__ == "__main__":
    unittest.main()
