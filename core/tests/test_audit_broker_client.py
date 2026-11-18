"""Stage F2.2 IPC client regression coverage without Docker or private keys."""
from __future__ import annotations

import base64
import json
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aura_core.osworld.audit_broker_protocol import BrokerDenied
from aura_core.osworld.audit_broker_receipt import SCHEMA, sign_measurement
from aura_core.osworld import audit_broker_client as client
from aura_core.osworld.isolation import BootIdentity, EXPECTED_PORTS, IMAGE, REQUIRED_CHECKS

AUDITOR = "S-1-5-21-111-222-333-1001"
BROKER = "S-1-5-21-111-222-333-1002"
AGENT = "S-1-5-21-111-222-333-1003"
RUN = "a" * 32
VM = "b" * 64
NOW = 1794000000


def public_bytes(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def measurement(nonce: str, checked_at: int = NOW) -> dict:
    boot = BootIdentity(VM, "d" * 64, "e" * 64, IMAGE, "f" * 64, "0" * 64)
    return {
        "schema": SCHEMA, "run_id": RUN, "container_id": VM,
        "nonce": nonce, "checked_at": checked_at,
        "boot": {
            "container_id": boot.container_id,
            "network_id": boot.network_id,
            "vm_sha256": boot.vm_sha256,
            "image": boot.image,
            "gateway_container_id": boot.gateway_container_id,
            "gateway_network_id": boot.gateway_network_id,
        },
        "host_ports": {
            str(p): f"127.0.0.1:{p + 20000}" for p in EXPECTED_PORTS
        },
        "checks": {name: True for name in REQUIRED_CHECKS},
    }


class FakeTransport:
    def __init__(self, key: Ed25519PrivateKey, mutate=None):
        self.key = key
        self.mutate = mutate
        self.calls = []

    def exchange(self, raw: bytes, *, expected_service_sid: str) -> bytes:
        self.calls.append((raw, expected_service_sid))
        request = json.loads(raw)
        claim = measurement(request["nonce"])
        if self.mutate is not None:
            claim = self.mutate(claim)
        signed = sign_measurement(claim, signer=self.key)
        return json.dumps(signed).encode("utf-8")


class BrokerClientTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.transport = FakeTransport(self.key)
        self.sid = patch.object(client, "current_process_sid", return_value=AUDITOR)
        self.clock = patch.object(client.time, "time", return_value=NOW)
        self.sid.start()
        self.clock.start()
        self.addCleanup(self.sid.stop)
        self.addCleanup(self.clock.stop)

    def request(self, **kw):
        config = {
            "run_id": RUN,
            "container_id": VM,
            "expected_auditor_sid": AUDITOR,
            "expected_service_sid": BROKER,
            "pinned_broker_public_key": public_bytes(self.key),
            "transport": self.transport,
        }
        config.update(kw)
        return client.request_signed_measurement(**config)

    def test_pinned_key_valid_measurement(self):
        verified = self.request()
        self.assertEqual(verified["run_id"], RUN)
        self.assertEqual(self.transport.calls[0][1], BROKER)

    def test_client_creates_fresh_nonce(self):
        self.request()
        self.request()
        messages = [json.loads(wire) for wire, _ in self.transport.calls]
        self.assertNotEqual(messages[0]["nonce"], messages[1]["nonce"])

    def test_raw_request_exposes_no_arbitrary_command(self):
        self.request()
        req = json.loads(self.transport.calls[0][0])
        self.assertEqual(
            set(req), {"protocol", "operation", "run_id", "container_id", "nonce", "issued_at"}
        )

    def test_wrong_auditor_account_rejected_before_ipc(self):
        with patch.object(client, "current_process_sid", return_value=AGENT):
            with self.assertRaises(BrokerDenied):
                self.request()
        self.assertEqual(self.transport.calls, [])

    def test_auditor_must_not_share_broker_sid(self):
        with self.assertRaises(BrokerDenied):
            self.request(expected_service_sid=AUDITOR)
        self.assertEqual(self.transport.calls, [])

    def test_invalid_broker_sid_rejected(self):
        with self.assertRaises(BrokerDenied):
            self.request(expected_service_sid="S-1-5-18")

    def test_missing_public_key_rejected(self):
        with self.assertRaises(BrokerDenied):
            self.request(pinned_broker_public_key=b"")

    def test_wrong_public_key_rejected(self):
        other = Ed25519PrivateKey.generate()
        with self.assertRaises(BrokerDenied):
            self.request(pinned_broker_public_key=public_bytes(other))

    def test_tampered_measurement_rejected(self):
        class Tamper(FakeTransport):
            def exchange(self, raw, *, expected_service_sid):
                signed = json.loads(super().exchange(raw, expected_service_sid=expected_service_sid))
                signed["run_id"] = "f" * 32
                return json.dumps(signed).encode()
        with self.assertRaises(BrokerDenied):
            self.request(transport=Tamper(self.key))

    def test_replayed_response_nonce_rejected(self):
        self.transport = FakeTransport(
            self.key, mutate=lambda c: {**c, "nonce": "e" * 32}
        )
        with self.assertRaises(BrokerDenied):
            self.request()

    def test_wrong_vm_binding_rejected(self):
        self.transport = FakeTransport(
            self.key, mutate=lambda c: {**c, "run_id": "f" * 32}
        )
        with self.assertRaises(BrokerDenied):
            self.request()

    def test_denied_response_cannot_become_signed_evidence(self):
        class Deny:
            def exchange(self, *_args, **_kwargs):
                return b'{"status":"ISOLATION_BLOCKED","signed":false}'
        with self.assertRaises(BrokerDenied):
            self.request(transport=Deny())

    def test_unsigned_response_rejected(self):
        class Unsigned:
            def exchange(self, message, **_kwargs):
                return json.dumps(measurement(json.loads(message)["nonce"])).encode()
        with self.assertRaises(BrokerDenied):
            self.request(transport=Unsigned())

    def test_oversized_response_rejected(self):
        class Oversized:
            def exchange(self, *_args, **_kwargs):
                return b"x" * (client.MAX_RESPONSE_BYTES + 1)
        with self.assertRaises(BrokerDenied):
            self.request(transport=Oversized())

    def test_duplicate_json_field_rejected(self):
        class Duplicates:
            def exchange(self, *_args, **_kwargs):
                return b'{"schema":"a","schema":"b"}'
        with self.assertRaises(BrokerDenied):
            self.request(transport=Duplicates())

    def test_non_bytes_response_rejected(self):
        class Invalid:
            def exchange(self, *_args, **_kwargs):
                return {"status": "ISOLATION_SIGNED"}
        with self.assertRaises(BrokerDenied):
            self.request(transport=Invalid())

    def test_expired_measurement_rejected(self):
        self.transport = FakeTransport(
            self.key, mutate=lambda c: {**c, "checked_at": NOW - 31}
        )
        with self.assertRaises(BrokerDenied):
            self.request()

    def test_negative_probe_result_rejected(self):
        def deny_one(c):
            c["checks"]["egress_v4_blocked"] = False
            return c
        self.transport = FakeTransport(self.key, mutate=deny_one)
        with self.assertRaises(BrokerDenied):
            self.request()

    def test_untrusted_platform_native_pipe_denied(self):
        import os
        if os.name != "nt":
            with self.assertRaises(BrokerDenied):
                client.WindowsBrokerPipe().exchange(b"{}", expected_service_sid=BROKER)

    def test_invalid_input_rejected_before_ipc(self):
        with self.assertRaises(BrokerDenied):
            self.request(container_id="bad")
        self.assertEqual(self.transport.calls, [])

    def test_server_token_lookup_requires_windows(self):
        import os
        if os.name != "nt":
            with self.assertRaises(BrokerDenied):
                client._server_process_sid(1)


    @unittest.skipUnless(__import__("os").name == "nt", "native Windows pipe only")
    def test_real_windows_pipe_transport_reads_deny_reply(self):
        """No service install or Docker: self-owned disposable IPC transport smoke."""
        import threading
        import win32file
        import win32pipe
        from aura_core.osworld.audit_broker_windows import current_process_sid as os_sid
        # The service-module denial is used only as a bounded response fixture.
        from aura_core.osworld.audit_broker_service import DENIED_RESPONSE
        created = threading.Event()
        problems = []

        def server():
            handle = None
            try:
                handle = win32pipe.CreateNamedPipe(
                    client.PIPE_NAME,
                    win32pipe.PIPE_ACCESS_DUPLEX,
                    win32pipe.PIPE_TYPE_MESSAGE |
                    win32pipe.PIPE_READMODE_MESSAGE |
                    win32pipe.PIPE_WAIT |
                    0x00000008,
                    1, 4096, 1024, 1000, None,
                )
                created.set()
                try:
                    win32pipe.ConnectNamedPipe(handle, None)
                except Exception as exc:
                    if getattr(exc, "winerror", None) != 535:
                        raise
                _, sent = win32file.ReadFile(handle, 1024)
                if sent != b"ping":
                    raise AssertionError("unexpected IPC request")
                win32file.WriteFile(handle, DENIED_RESPONSE)
                win32file.FlushFileBuffers(handle)
            except Exception as exc:
                problems.append(exc)
            finally:
                if handle is not None:
                    handle.Close()
                created.set()

        worker = threading.Thread(target=server, daemon=True)
        worker.start()
        self.assertTrue(created.wait(3), "Native pipe server did not start")
        data = client.WindowsBrokerPipe().exchange(
            b"ping", expected_service_sid=os_sid(),
        )
        self.assertEqual(data, DENIED_RESPONSE)
        worker.join(3)
        self.assertFalse(problems, f"Native named-pipe errors: {problems}")


if __name__ == "__main__":
    unittest.main()
