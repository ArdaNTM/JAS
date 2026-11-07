"""F2.6 P0/P1 security regressions: no real SSH, SCM or Docker used."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import errno
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from aura_core.osworld.audit_broker_protocol import BrokerDenied
from aura_core.osworld import audit_broker_ubuntu_transport as host
from aura_core.osworld import network_audit
from aura_core.osworld.audit_broker_service import BrokerServicePolicy

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


import importlib
policy = importlib.import_module("aura_ubuntu_broker_policy")
helper = load("aura_ubuntu_helper_test", SCRIPTS / "aura_ubuntu_broker_helper.py")
front = load("aura_ubuntu_front_test", SCRIPTS / "aura_ubuntu_broker_forced_command.py")

VM = "a" * 64
RUN = "b" * 32
NONCE = "c" * 32
GATEWAY_ID = "d" * 64
NOW = 1794000000


def request(op: str = "inspect_container", target: str = VM, **kw) -> bytes:
    return host.make_request(op, target, run_id=RUN, vm_id=VM,
                             nonce=NONCE, issued_at=NOW, **kw)


class FakeDocker:
    def __init__(self):
        self.calls: list[list[str]] = []
        self.vm = {
            "Id": VM,
            "State": {"Running": True},
            "Config": {"Image": policy.VM_IMAGE, "Labels": {policy.RUN_LABEL: RUN}},
            "HostConfig": {"NetworkMode": policy.NETWORK},
            "NetworkSettings": {"Networks": {policy.NETWORK: {"NetworkID": "1" * 64}}},
            "Mounts": [{"Type": "volume", "Name": policy.STORAGE + RUN, "Destination": "/storage"}],
        }
        self.gateway = {
            "Id": GATEWAY_ID,
            "Name": "/" + policy.GATEWAY + RUN,
            "State": {"Running": True},
            "Config": {"Labels": {policy.RUN_LABEL: RUN, "aura.osworld.role": "loopback-gateway"}},
            "NetworkSettings": {"Networks": {
                policy.NETWORK: {"NetworkID": "1" * 64},
                policy.INGRESS + RUN: {"NetworkID": "2" * 64},
            }},
        }
        self.internal = {
            "Name": policy.NETWORK, "Id": "1" * 64, "Internal": True,
            "Driver": "bridge", "IPAM": {"Config": [{"Gateway": "172.17.0.1"}]},
        }
        self.ingress = {
            "Name": policy.INGRESS + RUN, "Id": "2" * 64,
            "Internal": False, "EnableIPv6": False, "Driver": "bridge",
            "Labels": {policy.RUN_LABEL: RUN, "aura.osworld.purpose": "loopback-ingress"},
            "IPAM": {"Config": [{"Gateway": "172.18.0.1"}]},
        }
        self.volume = {
            "Name": policy.STORAGE + RUN, "Driver": "local",
            "Labels": {policy.RUN_LABEL: RUN, "aura.osworld.purpose": "vm-storage"},
        }
        self.errno = errno.ENETUNREACH

    def __call__(self, args, *, timeout=20):
        self.calls.append(list(args))
        if args == ["inspect", VM]:
            return [self.vm]
        if args == ["inspect", policy.GATEWAY + RUN]:
            return [self.gateway]
        if args == ["network", "inspect", policy.NETWORK]:
            return [self.internal]
        if args == ["network", "inspect", policy.INGRESS + RUN]:
            return [self.ingress]
        if args == ["volume", "inspect", policy.STORAGE + RUN]:
            return [self.volume]
        if args and args[0] == "run":
            info = json.loads(args[-1])
            return {
                "schema": policy.PROBE_SCHEMA, "name": info["name"],
                "errno": self.errno, "blocked": self.errno == errno.ENETUNREACH,
            }
        raise AssertionError("unexpected Docker args: " + repr(args))


class TransportProtocolTests(unittest.TestCase):
    def test_schema_and_pinned_images_consistent(self):
        self.assertEqual(host.REQUEST_SCHEMA, policy.REQUEST_SCHEMA)
        self.assertEqual(host.RESPONSE_SCHEMA, policy.RESPONSE_SCHEMA)
        self.assertEqual(host.REMOTE_COMMAND, front.REMOTE_COMMAND)
        self.assertEqual(host.REMOTE_IP, "192.168.247.2")
        self.assertEqual(policy.PROBE_IMAGE, network_audit.GATEWAY_IMAGE)
        self.assertEqual(policy.VM_IMAGE, network_audit.IMAGE)

    def test_exact_roundtrip_of_every_inspect(self):
        for name, target in [
            ("inspect_container", VM),
            ("inspect_gateway", policy.GATEWAY + RUN),
            ("inspect_network", policy.NETWORK),
            ("inspect_network", policy.INGRESS + RUN),
            ("inspect_volume", policy.STORAGE + RUN),
        ]:
            with self.subTest(name=name):
                data = policy.parse_request(request(name, target), now=NOW)
                self.assertEqual(data["run_id"], RUN)
                self.assertEqual(data["vm_id"], VM)
                self.assertEqual(data["target"], target)

    def test_client_refuses_unbound_or_wrong_run_resource(self):
        for operation, target in [
            ("inspect_container", "f" * 64),
            ("inspect_gateway", policy.GATEWAY + "e" * 32),
            ("inspect_network", policy.INGRESS + "e" * 32),
            ("inspect_volume", policy.STORAGE + "e" * 32),
            ("exec", VM), ("run", VM), ("inspect_network", "bridge"),
        ]:
            with self.subTest(operation=operation), self.assertRaises(BrokerDenied):
                request(operation, target)

    def test_server_refuses_tampered_run_vm_or_unauthorized_fields(self):
        original = json.loads(request())
        for delta in [
            {"vm_id": "f" * 64},
            {"operation": "docker run"}, {"target": "f" * 64},
            {"extra": "--privileged"}, {"issued_at": NOW - 60},
        ]:
            data = dict(original, **delta)
            with self.subTest(delta=delta), self.assertRaises(policy.Denied):
                policy.parse_request(json.dumps(data).encode(), now=NOW)

    def test_duplicate_json_keys_and_replay_window_rejected(self):
        raw = request()
        with self.assertRaises(policy.Denied):
            policy.parse_request(raw[:-1] + b',"nonce":"' + NONCE.encode() + b'"}', now=NOW)
        with self.assertRaises(policy.Denied):
            policy.parse_request(raw, now=NOW + 31)

    def test_fixed_probe_targets_cannot_be_overridden(self):
        for fields in [
            {"probe_name": "shell"},
            {"probe_name": "egress_v4_blocked", "gateway_ip": "1.1.1.1"},
            {"probe_name": "host_gateway_blocked", "gateway_ip": "1.1.1.1", "port": 22},
            {"probe_name": "host_gateway_blocked", "gateway_ip": "172.17.0.1", "port": 1234},
        ]:
            with self.subTest(fields=fields), self.assertRaises(BrokerDenied):
                request("probe", VM, **fields)

    def test_ssh_frontend_never_accepts_arbitrary_commands(self):
        with patch.dict(os.environ, {"SSH_ORIGINAL_COMMAND": "docker run --privileged"}):
            self.assertEqual(front.main(), 2)
        self.assertNotIn("docker", front.__dict__)
        self.assertNotIn("subprocess", front.__dict__)

    def test_pinned_ssh_command_disables_agent_and_forwarding(self):
        argv = host._ssh_argv()
        self.assertEqual(argv[-3:], ["--", host.REMOTE_IP, host.REMOTE_COMMAND])
        joined = " ".join(argv)
        for option in ("-F none", "BatchMode=yes", "StrictHostKeyChecking=yes",
                       "HostKeyAlgorithms=ssh-ed25519", "IdentitiesOnly=yes",
                       "ClearAllForwardings=yes", "ForwardAgent=no",
                       "PasswordAuthentication=no", "ProxyCommand=none"):
            self.assertIn(option, joined)
        self.assertNotIn("docker.exe", joined)

    def test_deny_only_cannot_activate_remote_ssh_even_with_fake_runner(self):
        data = BrokerServicePolicy(
            "S-1-5-21-1-2-3-1001", "S-1-5-21-1-2-3-1002",
            "S-1-5-21-1-2-3-1003", "deny_only",
        )
        with (patch.object(host, "verify_trusted_runtime"),
              patch.object(host, "load_service_policy", return_value=data),
              patch.object(host, "verify_registered_service_account") as scm):
            with self.assertRaises(BrokerDenied):
                host.UbuntuBrokerSshTransport(runner=Mock()).exchange(
                    "inspect_container", VM, run_id=RUN, vm_id=VM)
            scm.assert_not_called()


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.docker = FakeDocker()

    def process(self, op="inspect_container", target=VM, **kw):
        return policy.process_request(
            request(op, target, **kw),
            claim_nonce=lambda *args: True,
            docker=self.docker, now=NOW,
        )

    def test_full_run_and_volume_network_gateway_ownership_pass(self):
        for op, target in [
            ("inspect_container", VM), ("inspect_gateway", policy.GATEWAY + RUN),
            ("inspect_network", policy.NETWORK),
            ("inspect_network", policy.INGRESS + RUN),
            ("inspect_volume", policy.STORAGE + RUN),
        ]:
            with self.subTest(op=op):
                result = json.loads(self.process(op, target))
                self.assertEqual(result["nonce"], NONCE)
                self.assertEqual(result["operation"], op)
                self.assertIsInstance(result["result"], list)

    def test_wrong_vm_run_label_fails_before_other_docker_calls(self):
        self.docker.vm["Config"]["Labels"][policy.RUN_LABEL] = "e" * 32
        with self.assertRaises(policy.Denied):
            self.process()
        self.assertEqual(len(self.docker.calls), 1)

    def test_wrong_vm_image_or_network_fails(self):
        self.docker.vm["Config"]["Image"] = "happysixd/osworld-docker:latest"
        with self.assertRaises(policy.Denied):
            self.process()
        self.docker.vm["Config"]["Image"] = policy.VM_IMAGE
        self.docker.vm["HostConfig"]["NetworkMode"] = "host"
        with self.assertRaises(policy.Denied):
            self.process()

    def test_gateway_name_same_but_wrong_label_fails(self):
        self.docker.gateway["Config"]["Labels"][policy.RUN_LABEL] = "f" * 32
        with self.assertRaises(policy.Denied):
            self.process("inspect_gateway", policy.GATEWAY + RUN)

    def test_network_same_name_but_wrong_id_fails(self):
        self.docker.internal["Id"] = "f" * 64
        with self.assertRaises(policy.Denied):
            self.process("inspect_network", policy.NETWORK)

    def test_ingress_same_name_but_wrong_label_or_attachment_fails(self):
        self.docker.ingress["Labels"]["aura.osworld.purpose"] = "unknown"
        with self.assertRaises(policy.Denied):
            self.process("inspect_network", policy.INGRESS + RUN)
        self.docker.ingress["Labels"]["aura.osworld.purpose"] = "loopback-ingress"
        self.docker.gateway["NetworkSettings"]["Networks"][policy.INGRESS + RUN]["NetworkID"] = "f" * 64
        with self.assertRaises(policy.Denied):
            self.process("inspect_network", policy.INGRESS + RUN)

    def test_volume_same_name_not_mounted_or_labeled_fails(self):
        self.docker.volume["Labels"][policy.RUN_LABEL] = "f" * 32
        with self.assertRaises(policy.Denied):
            self.process("inspect_volume", policy.STORAGE + RUN)
        self.docker.volume["Labels"][policy.RUN_LABEL] = RUN
        self.docker.vm["Mounts"].clear()
        with self.assertRaises(policy.Denied):
            self.process("inspect_volume", policy.STORAGE + RUN)

    def test_gateway_probe_is_bound_to_exact_measured_id(self):
        raw = self.process("probe", GATEWAY_ID, probe_name="egress_v4_blocked")
        self.assertTrue(json.loads(raw)["result"]["blocked"])
        self.assertIn("container:" + GATEWAY_ID, next(x for x in self.docker.calls if x[0] == "run"))
        with self.assertRaises(policy.Denied):
            self.process("probe", "f" * 64, probe_name="egress_v4_blocked")

    def test_gateway_ip_must_match_authoritative_bridge_inspection(self):
        with self.assertRaises(policy.Denied):
            self.process("probe", VM, probe_name="host_gateway_blocked",
                         gateway_ip="172.19.0.1", port=22)
        result = json.loads(self.process(
            "probe", VM, probe_name="host_gateway_blocked",
            gateway_ip="172.17.0.1", port=22,
        ))
        self.assertTrue(result["result"]["blocked"])

    def test_timeout_or_refused_is_not_isolation_proof(self):
        self.docker.errno = errno.ECONNREFUSED
        result = json.loads(self.process("probe", VM, probe_name="metadata_blocked"))
        self.assertFalse(result["result"]["blocked"])
        self.docker.errno = errno.ETIMEDOUT
        result = json.loads(self.process("probe", VM, probe_name="metadata_blocked"))
        self.assertFalse(result["result"]["blocked"])

    def test_root_docker_runner_has_no_privileged_or_mount_flags(self):
        self.process("probe", VM, probe_name="egress_v4_blocked")
        cmd = next(args for args in self.docker.calls if args[0] == "run")
        for item in ("--cap-drop", "ALL", "--read-only", "--pull", "never",
                     "--user", "65534:65534", "--network", "container:" + VM):
            self.assertIn(item, cmd)
        for item in ("--privileged", "--mount", "--volume", "--network=host"):
            self.assertNotIn(item, cmd)


class PersistentReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "nonce.sqlite3"
        self.store = helper.DurableNonceStore(self.path, enforce_root=False)

    def test_atomic_nonce_consumption_survives_store_reopen(self):
        self.assertTrue(self.store.claim(NONCE, RUN, VM))
        reopened = helper.DurableNonceStore(self.path, enforce_root=False)
        self.assertFalse(reopened.claim(NONCE, RUN, VM))

    def test_nonce_replay_with_new_run_cannot_reopen(self):
        self.assertTrue(self.store.claim(NONCE, RUN, VM))
        self.assertFalse(self.store.claim(NONCE, "e" * 32, VM))

    def test_multiple_concurrent_claims_have_one_winner(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.store.claim(NONCE, RUN, VM), range(12)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 11)

    def test_nonce_consumed_before_any_docker_inspection(self):
        docker = FakeDocker()
        raw = request()
        policy.process_request(raw, claim_nonce=self.store.claim, docker=docker, now=NOW)
        count = len(docker.calls)
        with self.assertRaises(policy.Denied):
            policy.process_request(raw, claim_nonce=self.store.claim, docker=docker, now=NOW)
        self.assertEqual(len(docker.calls), count)

    def test_nonce_store_rejects_malformed_nonce(self):
        with self.assertRaises(policy.Denied):
            self.store.claim("../state", RUN, VM)


class LinuxPeerBoundaryTests(unittest.TestCase):
    def test_no_socket_credentials_is_not_accepted(self):
        with patch.object(helper.socket, "SO_PEERCRED", None, create=True):
            conn = Mock()
            conn.family = socket.AF_UNIX
            with self.assertRaises((policy.Denied, TypeError)):
                helper._peer_uid(conn)

    @unittest.skipUnless(hasattr(socket, "SO_PEERCRED"), "Linux-only kernel peer credentials")
    def test_real_socketpair_kernel_peer_uid(self):
        with socket.socketpair() as (a, b):
            if os.getuid() == 0:
                self.skipTest("CI test expects non-root Linux job")
            self.assertEqual(helper._peer_uid(a), os.getuid())

    def test_wrong_peer_denied_before_nonce_and_docker(self):
        conn = Mock()
        store = Mock()
        with patch.object(helper, "_peer_uid", return_value=999):
            with self.assertRaises(policy.Denied):
                helper.handle_connection(conn, store=store, expected_uid=1001)
        store.claim.assert_not_called()
        conn.recv.assert_not_called()

    def test_systemd_socket_activation_is_mandatory(self):
        with patch.dict(os.environ, {"LISTEN_FDS": "0", "LISTEN_PID": "12345"}):
            with self.assertRaises(policy.Denied):
                helper._systemd_listener()

    def test_no_deployed_scm_or_signing(self):
        import aura_core.osworld.audit_broker_service as scm
        self.assertIn("deny_only", scm.parse_service_policy.__code__.co_consts)
        self.assertNotIn("UbuntuDockerAuditBackend", scm.__dict__)


class BackendContractTests(unittest.TestCase):
    def setUp(self):
        def runner(cmd, **kw):
            body = json.loads(kw["input"])
            if body["operation"] == "probe":
                value = {"schema": policy.PROBE_SCHEMA, "name": body["probe_name"],
                         "errno": errno.ENETUNREACH, "blocked": True}
            else:
                value = [{"Id": GATEWAY_ID if body["operation"] == "inspect_gateway" else VM}]
            reply = {"schema": host.RESPONSE_SCHEMA, "operation": body["operation"],
                     "nonce": body["nonce"], "result": value}
            return SimpleNamespace(returncode=0, stdout=json.dumps(reply).encode(), stderr=b"")
        self.addCleanup(patch.stopall)
        self.patcher = patch.object(host, "_production_preflight")
        self.patcher.start()
        self.transport = host.UbuntuBrokerSshTransport(runner=runner)
        self.backend = host.UbuntuDockerAuditBackend(
            transport=self.transport, run_id=RUN, vm_id=VM)

    def test_pinned_backend_inspect_api(self):
        self.assertEqual(self.backend.inspect_container(VM), [{"Id": VM}])
        self.assertEqual(self.backend.inspect_gateway(RUN), [{"Id": GATEWAY_ID}])
        self.assertEqual(self.backend.inspect_network(network_audit.NETWORK_NAME), [{"Id": VM}])
        self.assertEqual(self.backend.inspect_volume(network_audit.STORAGE_VOLUME_PREFIX + RUN), [{"Id": VM}])

    def test_cannot_inspect_other_run_even_if_name_matches_pattern(self):
        with self.assertRaises(BrokerDenied):
            self.backend.inspect_gateway("f" * 32)
        with self.assertRaises(BrokerDenied):
            self.backend.inspect_container("f" * 64)
        with self.assertRaises(BrokerDenied):
            self.backend.inspect_volume(network_audit.STORAGE_VOLUME_PREFIX + "f" * 32)

    def test_fixed_probes_on_vm_and_measured_gateway(self):
        self.assertTrue(self.backend.fixed_probe(container_id=VM, name="egress_v4_blocked"))
        self.assertFalse(self.backend.fixed_probe(container_id=GATEWAY_ID, name="egress_v4_blocked"))
        self.backend.inspect_gateway(RUN)
        self.assertTrue(self.backend.fixed_probe(container_id=GATEWAY_ID, name="egress_v4_blocked"))
        self.assertFalse(self.backend.fixed_probe(container_id="f" * 64, name="egress_v4_blocked"))

    def test_trusted_runner_never_inherits_hostile_docker_env(self):
        with patch.dict(os.environ, {
            "DOCKER_HOST": "tcp://attacker:2375", "DOCKER_CONTEXT": "attacker",
            "SSH_AUTH_SOCK": "/tmp/attacker.sock",
        }):
            self.assertEqual(self.backend.inspect_container(VM), [{"Id": VM}])

    def test_remote_spoofed_signature_never_accepted_as_receipt(self):
        data = json.dumps({"status": "ISOLATION_SIGNED"}).encode()
        with self.assertRaises(BrokerDenied):
            host.parse_response(data, nonce=NONCE, operation="inspect_container")


if __name__ == "__main__":
    unittest.main()
