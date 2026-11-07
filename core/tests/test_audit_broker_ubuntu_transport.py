"""F2.6 isolated Ubuntu SSH broker: fake-only positive and adversarial tests."""
from __future__ import annotations

import errno
import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aura_core.osworld.audit_broker_protocol import BrokerDenied
from aura_core.osworld import audit_broker_ubuntu_transport as host
from aura_core.osworld import network_audit

VM = "a" * 64
RUN = "b" * 32
NONCE = "c" * 32
NOW = 1794000000

GUEST_PATH = Path(__file__).resolve().parents[1] / "scripts" / "aura_ubuntu_broker_forced_command.py"
SPEC = importlib.util.spec_from_file_location("aura_ubuntu_forced_test", GUEST_PATH)
assert SPEC is not None and SPEC.loader is not None
GUEST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUEST)


class RequestContractTests(unittest.TestCase):
    def make(self, op="inspect_container", target=VM, **kwargs):
        return host.make_request(op, target, nonce=NONCE, issued_at=NOW, **kwargs)

    def test_client_guest_contract_exactly_matches(self):
        data = GUEST.parse_request(self.make(), now=NOW)
        self.assertEqual(data["target"], VM)
        self.assertEqual(data["nonce"], NONCE)
        self.assertEqual(GUEST.REQUEST_SCHEMA, host.REQUEST_SCHEMA)
        self.assertEqual(GUEST.RESPONSE_SCHEMA, host.RESPONSE_SCHEMA)
        self.assertEqual(GUEST.PROBE_IMAGE, network_audit.GATEWAY_IMAGE)

    def test_allowlisted_inspections_roundtrip(self):
        targets = [
            ("inspect_container", VM),
            ("inspect_gateway", GUEST.GATEWAY + RUN),
            ("inspect_network", GUEST.NETWORK),
            ("inspect_network", GUEST.INGRESS + RUN),
            ("inspect_volume", GUEST.STORAGE + RUN),
        ]
        for op, target in targets:
            with self.subTest(op=op, target=target):
                self.assertEqual(GUEST.parse_request(self.make(op, target), now=NOW)["target"], target)

    def test_arbitrary_actions_names_and_mounts_denied(self):
        attempts = [
            ("exec", VM), ("run", VM), ("mount", VM),
            ("inspect_container", "bridge"),
            ("inspect_gateway", "evil"),
            ("inspect_network", "bridge"),
            ("inspect_network", GUEST.INGRESS + "../../"),
            ("inspect_volume", "secrets"),
        ]
        for op, target in attempts:
            with self.subTest(op=op, target=target), self.assertRaises(BrokerDenied):
                self.make(op, target)

    def test_no_client_chosen_probes(self):
        for values in [
            {"probe_name": "curl"},
            {"probe_name": "egress_v4_blocked", "gateway_ip": "1.1.1.1"},
            {"probe_name": "host_gateway_blocked", "gateway_ip": "1.1.1.1", "port": 22},
            {"probe_name": "host_gateway_blocked", "gateway_ip": "172.17.0.1", "port": 1234},
        ]:
            with self.subTest(values=values), self.assertRaises(BrokerDenied):
                self.make("probe", VM, **values)

    def test_probe_positive_and_guest_rejects_unapproved_fields(self):
        raw = self.make("probe", VM, probe_name="host_gateway_blocked", gateway_ip="172.17.0.1", port=22)
        self.assertEqual(GUEST.parse_request(raw, now=NOW)["port"], 22)
        data = json.loads(raw)
        data["docker_args"] = ["--privileged"]
        with self.assertRaises(GUEST.Denied):
            GUEST.parse_request(json.dumps(data).encode(), now=NOW)

    def test_duplicate_json_fields_and_stale_or_future_nonce(self):
        raw = self.make()
        with self.assertRaises(GUEST.Denied):
            GUEST.parse_request(raw[:-1] + b',"nonce":"' + NONCE.encode() + b'"}', now=NOW)
        with self.assertRaises(GUEST.Denied):
            GUEST.parse_request(raw, now=NOW + 40)
        with self.assertRaises(GUEST.Denied):
            GUEST.parse_request(raw, now=NOW - 6)

    def test_guest_refuses_unknown_linux_commands(self):
        with patch.dict(GUEST.os.environ, {"SSH_ORIGINAL_COMMAND": "docker run --privileged"}):
            self.assertEqual(GUEST.main(), 2)


class ResponseContractTests(unittest.TestCase):
    def response(self, result=None, **extra):
        data = {"schema": host.RESPONSE_SCHEMA, "operation": "inspect_container",
                "nonce": NONCE, "result": [{"Id": VM}] if result is None else result}
        data.update(extra)
        return json.dumps(data).encode()

    def test_valid_inspection(self):
        self.assertEqual(host.parse_response(self.response(), nonce=NONCE, operation="inspect_container"), [{"Id": VM}])

    def test_wrong_nonce_or_extra_field_rejected(self):
        for x in [self.response(nonce="d" * 32), self.response(approved=True),
                  self.response(operation="exec")]:
            with self.assertRaises(BrokerDenied):
                host.parse_response(x, nonce=NONCE, operation="inspect_container")

    def test_duplicate_and_oversized_reply_rejected(self):
        with self.assertRaises(BrokerDenied):
            host.parse_response(self.response()[:-1] + b',"nonce":"' + NONCE.encode() + b'"}',
                                nonce=NONCE, operation="inspect_container")
        with self.assertRaises(BrokerDenied):
            host.parse_response(b"x" * (host.MAX_OUTPUT + 1), nonce=NONCE, operation="inspect_container")

    def test_probe_success_not_confused_with_isolation_receipt(self):
        data = {"schema": host.RESPONSE_SCHEMA, "operation": "probe", "nonce": NONCE,
                "result": {"schema": "aura.osworld.network-probe.v1",
                           "name": "egress_v4_blocked", "errno": errno.ENETUNREACH, "blocked": True}}
        value = host.parse_response(json.dumps(data).encode(), nonce=NONCE, operation="probe")
        self.assertIs(value["blocked"], True)
        self.assertNotIn("ISOLATION_SIGNED", json.dumps(data))


class PinnedSshTests(unittest.TestCase):
    def test_ssh_uses_fixed_host_identity_and_forbids_tunnels(self):
        argv = host._ssh_argv()
        self.assertEqual(argv[-4:], ["-l", host.REMOTE_USER, "--", host.REMOTE_IP, host.REMOTE_COMMAND][-4:])
        joined = " ".join(argv)
        for part in ("StrictHostKeyChecking=yes", "BatchMode=yes", "PasswordAuthentication=no",
                     "ClearAllForwardings=yes", "ProxyCommand=none", "ForwardAgent=no",
                     "-F none", "HostKeyAlgorithms=ssh-ed25519"):
            self.assertIn(part, joined)
        for part in ("docker.exe", "-p 2375", "--privileged", "ssh-agent"):
            self.assertNotIn(part, joined)

    def test_ssh_runner_only_gets_json_stdin_no_unsafe_env(self):
        seen = []
        def runner(cmd, **kw):
            seen.append((cmd, kw))
            req = json.loads(kw["input"])
            out = {"schema": host.RESPONSE_SCHEMA, "operation": req["operation"],
                   "nonce": req["nonce"], "result": [{"Id": VM}]}
            return SimpleNamespace(returncode=0, stdout=json.dumps(out).encode(), stderr=b"")
        transport = host.UbuntuBrokerSshTransport(runner=runner)
        self.assertEqual(transport.exchange("inspect_container", VM), [{"Id": VM}])
        cmd, kw = seen[0]
        self.assertIs(kw["shell"], False)
        self.assertIsInstance(kw["input"], bytes)
        self.assertNotIn("DOCKER_HOST", kw["env"])
        self.assertNotIn("SSH_AUTH_SOCK", kw["env"])
        self.assertNotIn(VM, cmd)

    def test_transport_failure_is_fail_closed(self):
        def bad_runner(*args, **kwargs):
            return SimpleNamespace(returncode=255, stdout=b"", stderr=b"connection refused")
        with self.assertRaises(BrokerDenied):
            host.UbuntuBrokerSshTransport(runner=bad_runner).exchange("inspect_container", VM)

    def test_release_guard_rejects_forged_server_reply(self):
        def forge(cmd, **kw):
            return SimpleNamespace(returncode=0, stdout=b'{"status":"ISOLATION_SIGNED"}', stderr=b"")
        with self.assertRaises(BrokerDenied):
            host.UbuntuBrokerSshTransport(runner=forge).exchange("inspect_container", VM)


class GuestBackendTests(unittest.TestCase):
    def test_guest_inspect_uses_fixed_docker_binary_and_socket(self):
        calls = []
        def runner(argv, **kw):
            calls.append((argv, kw))
            return SimpleNamespace(returncode=0, stdout=b'[{"Id":"' + VM.encode() + b'"}]', stderr=b"")
        with (patch.object(GUEST.os.path, "isfile", return_value=True),
              patch.object(GUEST.os.path, "islink", return_value=False),
              patch.object(GUEST.subprocess, "run", side_effect=runner)):
            self.assertIsInstance(GUEST._docker(["inspect", VM]), list)
        argv, kw = calls[0]
        self.assertEqual(argv[:5], [GUEST.DOCKER, "--host", GUEST.DOCKER_SOCKET,
                                    "--config", GUEST.DOCKER_CONFIG])
        self.assertFalse(kw["shell"])
        self.assertNotIn("DOCKER_HOST", kw["env"])

    def test_probe_requires_real_running_aura_container(self):
        with patch.object(GUEST, "_docker", return_value=[{"Id": VM, "Config": {"Labels": {}}, "State": {"Running": True}}]):
            with self.assertRaises(GUEST.Denied):
                GUEST._require_aura_container(VM)

    def test_gateway_probe_no_external_target(self):
        data = json.loads(host.make_request("probe", VM, nonce=NONCE, issued_at=NOW,
                                            probe_name="host_gateway_blocked",
                                            gateway_ip="172.17.0.1", port=22))
        with patch.object(GUEST, "_docker", return_value={"schema": "aura.osworld.network-probe.v1",
                                                          "name": "host_gateway_blocked", "errno": 0, "blocked": False}) as dock:
            with patch.object(GUEST, "_require_aura_container"):
                self.assertFalse(GUEST.execute(data)["blocked"])
        args = dock.call_args.args[0]
        self.assertNotIn("--privileged", args)
        self.assertNotIn("--mount", args)
        self.assertIn("--read-only", args)
        self.assertIn("--pull", args)
        self.assertIn("never", args)
        self.assertIn("container:" + VM, args)
        self.assertEqual(args[args.index("--network") + 1], "container:" + VM)

    def test_connection_refused_is_never_isolation_proof(self):
        data = json.loads(host.make_request("probe", VM, nonce=NONCE, issued_at=NOW,
                                            probe_name="egress_v4_blocked"))
        with (patch.object(GUEST, "_require_aura_container"),
              patch.object(GUEST, "_docker", return_value={"schema": "aura.osworld.network-probe.v1",
                                                          "name": "egress_v4_blocked", "errno": errno.ECONNREFUSED,
                                                          "blocked": True})):
            self.assertFalse(GUEST.execute(data)["blocked"])

    def test_service_is_not_activated(self):
        import aura_core.osworld.audit_broker_service as service
        self.assertIn('deny_only', service.parse_service_policy.__code__.co_consts)
        # No imports from the deployed service to Ubuntu backend are introduced.
        self.assertNotIn("UbuntuDockerAuditBackend", service.__dict__)


if __name__ == "__main__":
    unittest.main()


class BackendCompatibilityTests(unittest.TestCase):
    def setUp(self):
        def fake_runner(cmd, **kw):
            request = json.loads(kw["input"])
            if request["operation"] == "probe":
                result = {"schema": "aura.osworld.network-probe.v1",
                          "name": request["probe_name"], "errno": errno.ENETUNREACH, "blocked": True}
            else:
                result = [{"Id": VM}]
            wire = {"schema": host.RESPONSE_SCHEMA, "operation": request["operation"],
                    "nonce": request["nonce"], "result": result}
            return SimpleNamespace(returncode=0, stdout=json.dumps(wire).encode(), stderr=b"")
        self.transport = host.UbuntuBrokerSshTransport(runner=fake_runner)
        self.backend = host.UbuntuDockerAuditBackend(transport=self.transport)

    def test_existing_inspect_backend_interface_is_preserved(self):
        from aura_core.osworld.audit_broker_docker import DockerAuditBackend
        self.assertIsInstance(self.backend, DockerAuditBackend)
        self.assertEqual(self.backend.inspect_container(VM), [{"Id": VM}])
        self.assertEqual(self.backend.inspect_gateway(RUN), [{"Id": VM}])
        self.assertEqual(self.backend.inspect_network(network_audit.NETWORK_NAME), [{"Id": VM}])
        self.assertEqual(self.backend.inspect_volume(network_audit.STORAGE_VOLUME_PREFIX + RUN), [{"Id": VM}])

    def test_backend_does_not_accept_arbitrary_inspect_flags(self):
        for args in (["run", "--privileged"], ["exec", VM, "sh"],
                     ["network", "inspect", "bridge"], ["inspect", "../var/run/docker.sock"]):
            with self.subTest(args=args), self.assertRaises(BrokerDenied):
                self.backend._invoke(args, timeout=5)

    def test_negative_probe_response_must_use_explicit_network_errno(self):
        self.assertTrue(self.backend._one_probe(
            VM, name="egress_v4_blocked", kind="tcp4", host="1.1.1.1", port=443,
        ))
        self.assertFalse(self.backend._one_probe(
            VM, name="egress_v4_blocked", kind="tcp4", host="8.8.8.8", port=443,
        ))

    def test_ssh_transport_literal_matches_linux_forced_command(self):
        self.assertEqual(host.REMOTE_COMMAND, GUEST.REMOTE_COMMAND)
        self.assertEqual(host.REMOTE_IP, "192.168.247.2")
