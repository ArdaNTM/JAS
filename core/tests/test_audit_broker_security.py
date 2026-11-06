"""Trust-boundary tests: no real Docker, Windows service or Owner secrets."""
from __future__ import annotations

import base64
import json
from pathlib import Path
import sqlite3
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aura_core.osworld.audit_broker_protocol import BrokerDenied
from aura_core.osworld.audit_broker_docker import (
    DOCKER_EXE, DockerAuditBackend,
)
from aura_core.osworld.audit_broker_receipt import (
    DurableNonceStore, SCHEMA, sign_measurement, verify_measurement,
)
from aura_core.osworld.audit_broker_windows import (
    PIPE_NAME, serve_once,
)
from aura_core.osworld.isolation import (
    BootIdentity, IMAGE, REQUIRED_CHECKS, EXPECTED_PORTS,
)

RUN = "a" * 32
CONTAINER = "b" * 64
NONCE = "c" * 32
NOW = 1794000000
AUDITOR_SID = "S-1-5-21-111-222-333-1001"
SERVICE_SID = "S-1-5-21-111-222-333-1002"
AGENT_SID = "S-1-5-21-111-222-333-1003"


def evidence():
    boot = BootIdentity(CONTAINER, "d" * 64, "e" * 64, IMAGE, "f" * 64, "0" * 64)
    return dict(
        schema=SCHEMA, run_id=RUN, container_id=CONTAINER,
        nonce=NONCE, checked_at=NOW,
        boot={
            "container_id": boot.container_id,
            "network_id": boot.network_id,
            "vm_sha256": boot.vm_sha256,
            "image": boot.image,
            "gateway_container_id": boot.gateway_container_id,
            "gateway_network_id": boot.gateway_network_id,
        },
        checks={key: True for key in REQUIRED_CHECKS},
        host_ports={str(p): "127.0.0.1:" + str(p + 20000) for p in EXPECTED_PORTS},
    )


def public_bytes(key):
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


class DurableNonceTests(unittest.TestCase):
    def setUp(self):
        from tempfile import TemporaryDirectory
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "nonces.sqlite"
        self.enterContext(patch("aura_core.osworld.audit_broker_receipt._verify_private_state_path"))
        self.enterContext(patch("aura_core.osworld.audit_broker_receipt._harden_state_file"))

    def test_first_claim_then_replay_rejected(self):
        store = DurableNonceStore(self.path)
        self.assertIs(store.claim(NONCE, now=NOW), True)
        self.assertIs(store.claim(NONCE, now=NOW + 1), False)

    def test_replay_rejected_after_process_restart(self):
        self.assertTrue(DurableNonceStore(self.path).claim(NONCE, now=NOW))
        self.assertFalse(DurableNonceStore(self.path).claim(NONCE, now=NOW))

    def test_distinct_nonce_allowed(self):
        store = DurableNonceStore(self.path)
        self.assertTrue(store.claim(NONCE, now=NOW))
        self.assertTrue(store.claim("f" * 32, now=NOW))

    def test_sqlite_unique_primary_key(self):
        store = DurableNonceStore(self.path)
        self.assertTrue(store.claim(NONCE, now=NOW))
        with sqlite3.connect(self.path) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    "INSERT INTO consumed_nonces (nonce, expires_at) VALUES (?, ?)",
                    (NONCE, NOW + 900),
                )

    def test_reject_invalid_nonce(self):
        store = DurableNonceStore(self.path)
        for nonce in ("INVALID", NONCE.upper(), "a" * 31, ""):
            with self.subTest(nonce=nonce), self.assertRaises(BrokerDenied):
                store.claim(nonce, now=NOW)

    def test_missing_parent_rejected(self):
        with self.assertRaises(BrokerDenied):
            DurableNonceStore(self.path.parent / "missing" / "store.sqlite")

    def test_reject_relative_store(self):
        with self.assertRaises(BrokerDenied):
            DurableNonceStore(Path("nonce.sqlite"))

    def test_replay_store_fail_closed_on_database_error(self):
        store = DurableNonceStore(self.path)
        store._connect = lambda: (_ for _ in ()).throw(sqlite3.OperationalError("offline"))
        with self.assertRaises(sqlite3.OperationalError):
            store.claim(NONCE, now=NOW)


class MeasurementTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.public = public_bytes(self.key)
        self.signed = sign_measurement(evidence(), signer=self.key)

    def verify(self, obj=None, **changes):
        args = {
            "pinned_public_key": self.public,
            "expected_nonce": NONCE,
            "expected_container_id": CONTAINER,
            "expected_run_id": RUN,
            "now": NOW,
        }
        args.update(changes)
        return verify_measurement(self.signed if obj is None else obj, **args)

    def test_valid_signature(self):
        self.assertEqual(self.verify()["run_id"], RUN)

    def test_changed_checks_cannot_be_signed_by_agent(self):
        tampered = {**self.signed, "checks": {**self.signed["checks"], "egress_v4_blocked": False}}
        with self.assertRaises(BrokerDenied):
            self.verify(tampered)

    def test_modified_signed_claim_rejected(self):
        tampered = {**self.signed, "host_ports": {**self.signed["host_ports"], "5000": "127.0.0.1:32000"}}
        with self.assertRaises(BrokerDenied):
            self.verify(tampered)

    def test_alternate_valid_broker_key_rejected(self):
        alternate = public_bytes(Ed25519PrivateKey.generate())
        with self.assertRaises(BrokerDenied):
            self.verify(pinned_public_key=alternate)

    def test_wrong_nonce_rejected(self):
        with self.assertRaises(BrokerDenied):
            self.verify(expected_nonce="d" * 32)

    def test_wrong_vm_identity_rejected(self):
        with self.assertRaises(BrokerDenied):
            self.verify(expected_container_id="a" * 64)

    def test_wrong_run_rejected(self):
        with self.assertRaises(BrokerDenied):
            self.verify(expected_run_id="d" * 32)

    def test_expired_measurement_rejected(self):
        with self.assertRaises(BrokerDenied):
            self.verify(now=NOW + 31)

    def test_future_measurement_rejected(self):
        with self.assertRaises(BrokerDenied):
            self.verify(now=NOW - 6)

    def test_unsigned_measurement_rejected(self):
        with self.assertRaises(BrokerDenied):
            self.verify(evidence())

    def test_bad_signature_length_rejected(self):
        malformed = {**self.signed, "signature_b64": base64.b64encode(b"x").decode()}
        with self.assertRaises(BrokerDenied):
            self.verify(malformed)

    def test_additional_untrusted_field_rejected(self):
        modified = {**self.signed, "docker_command": "run"}
        with self.assertRaises(BrokerDenied):
            self.verify(modified)

    def test_negative_network_check_rejected(self):
        invalid = evidence()
        invalid["checks"]["gateway_metadata_blocked"] = False
        with self.assertRaises(BrokerDenied):
            sign_measurement(invalid, signer=self.key)

    def test_unpinned_runtime_image_rejected(self):
        invalid = evidence()
        invalid["boot"]["image"] = "alpine:latest"
        with self.assertRaises(Exception):
            sign_measurement(invalid, signer=self.key)

    def test_loopback_enforced(self):
        invalid = evidence()
        invalid["host_ports"]["5000"] = "0.0.0.0:5000"
        with self.assertRaises(BrokerDenied):
            sign_measurement(invalid, signer=self.key)


class FakeDocker:
    def __init__(self):
        self.calls = []
        self.stdout = "[]"
        self.returncode = 0

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        return SimpleNamespace(
            returncode=self.returncode,
            stdout="AURA_DENIED" if argv[1] == "run" else self.stdout,
            stderr="",
        )


class DockerBackendTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeDocker()
        self.backend = DockerAuditBackend(runner=self.fake)

    def test_container_inspection_pinned(self):
        self.backend.inspect_container(CONTAINER)
        self.assertEqual(
            self.fake.calls[-1][0],
            [str(DOCKER_EXE), "inspect", CONTAINER],
        )

    def test_gateway_inspection_pinned(self):
        self.backend.inspect_gateway(RUN)
        self.assertEqual(
            self.fake.calls[-1][0][-1],
            "aura-osworld-v21-gateway-" + RUN,
        )

    def test_volume_and_network_name_allowlist(self):
        self.backend.inspect_volume("aura-osworld-v21-storage-" + RUN)
        self.backend.inspect_network("aura-osworld-v21-lab")
        self.backend.inspect_network("aura-osworld-v21-ingress-" + RUN)
        self.assertEqual(len(self.fake.calls), 3)

    def test_unknown_volume_and_network_rejected(self):
        for thunk in (
            lambda: self.backend.inspect_volume("important_data"),
            lambda: self.backend.inspect_network("bridge"),
            lambda: self.backend.inspect_network("host"),
        ):
            with self.assertRaises(BrokerDenied):
                thunk()
        self.assertEqual(self.fake.calls, [])

    def test_command_injection_as_container_id_rejected(self):
        with self.assertRaises(BrokerDenied):
            self.backend.inspect_container(CONTAINER + ";rm -rf /")
        self.assertEqual(self.fake.calls, [])

    def test_fixed_egress_probe_has_no_privileges(self):
        self.assertTrue(self.backend.fixed_probe(
            container_id=CONTAINER, name="egress_v4_blocked",
        ))
        argv, kwargs = self.fake.calls[-1]
        self.assertIn("--cap-drop", argv)
        self.assertIn("ALL", argv)
        self.assertIn("--security-opt", argv)
        self.assertIn("no-new-privileges", argv)
        self.assertEqual(kwargs["shell"], False)
        self.assertEqual(kwargs["timeout"], 30)
        self.assertEqual(argv[argv.index("--network") + 1], "container:" + CONTAINER)

    def test_arbitrary_probe_rejected(self):
        with self.assertRaises(BrokerDenied):
            self.backend.fixed_probe(container_id=CONTAINER, name="sh -c docker")
        self.assertEqual(self.fake.calls, [])

    def test_gateway_cannot_be_public_ip(self):
        with self.assertRaises(BrokerDenied):
            self.backend.fixed_probe(
                container_id=CONTAINER, name="host_gateway_blocked",
                gateway_ip="8.8.8.8",
            )
        self.assertEqual(self.fake.calls, [])

    def test_probe_connection_detected_or_tool_failure_does_not_pass(self):
        self.fake.returncode = 3
        self.assertFalse(self.backend.fixed_probe(
            container_id=CONTAINER, name="metadata_blocked",
        ))

    def test_invalid_inspect_json_denied(self):
        self.fake.stdout = "not JSON"
        with self.assertRaises(BrokerDenied):
            self.backend.inspect_container(CONTAINER)

    def test_docker_path_cannot_be_overridden(self):
        with self.assertRaises(BrokerDenied):
            DockerAuditBackend(
                executable=Path("C:/other/docker.exe"), runner=self.fake,
            )


class WindowsIPCContractTests(unittest.TestCase):
    def test_pinned_name(self):
        self.assertEqual(PIPE_NAME, r"\\.\pipe\aura-osworld-audit-v1")

    def test_service_same_as_agent_rejected_before_windows_calls(self):
        with patch(
            "aura_core.osworld.audit_broker_windows.current_process_sid",
            return_value=AGENT_SID,
        ):
            with self.assertRaises(BrokerDenied):
                serve_once(
                    auditor_sid=AUDITOR_SID,
                    expected_service_sid=AGENT_SID,
                    forbidden_agent_sid=AGENT_SID,
                    handler=lambda *_: b"{}",
                )

    def test_service_same_as_auditor_rejected_before_windows_calls(self):
        with patch(
            "aura_core.osworld.audit_broker_windows.current_process_sid",
            return_value=AUDITOR_SID,
        ):
            with self.assertRaises(BrokerDenied):
                serve_once(
                    auditor_sid=AUDITOR_SID,
                    expected_service_sid=AUDITOR_SID,
                    forbidden_agent_sid=AGENT_SID,
                    handler=lambda *_: b"{}",
                )

    def test_untrusted_platform_cannot_start_transport(self):
        with patch(
            "aura_core.osworld.audit_broker_windows.current_process_sid",
            return_value=SERVICE_SID,
        ):
            if __import__("os").name != "nt":
                with self.assertRaises(BrokerDenied):
                    serve_once(
                        auditor_sid=AUDITOR_SID,
                        expected_service_sid=SERVICE_SID,
                        forbidden_agent_sid=AGENT_SID,
                        handler=lambda *_: b"{}",
                    )


if __name__ == "__main__":
    unittest.main()
