"""Docker-free regression tests for the fail-closed audit request protocol."""
import json
import unittest

from aura_core.osworld.audit_broker_protocol import (
    AuditRequest,
    BrokerDenied,
    OPERATION,
    PROTOCOL,
    authorize_request,
    parse_request,
)

NOW = 1794000000
RUN = "a" * 32
CONTAINER = "b" * 64
SID = "S-1-5-21-111-222-333-1001"


def message(**changes):
    obj = {
        "protocol": PROTOCOL,
        "operation": OPERATION,
        "run_id": RUN,
        "container_id": CONTAINER,
        "nonce": "c" * 32,
        "issued_at": NOW,
    }
    obj.update(changes)
    return json.dumps(obj).encode("utf-8")


class Nonces:
    def __init__(self):
        self.used = set()

    def claim(self, nonce):
        if nonce in self.used:
            return False
        self.used.add(nonce)
        return True


def authorization(**changes):
    kwargs = dict(
        now=NOW,
        peer_sid=SID,
        auditor_sid=SID,
        measured_run_id=RUN,
        measured_container_id=CONTAINER,
        claim_nonce=Nonces().claim,
    )
    kwargs.update(changes)
    return kwargs


class AuditBrokerProtocolTests(unittest.TestCase):
    def test_valid_request_authorized(self):
        req = parse_request(message(), now=NOW)
        self.assertEqual(req.run_id, RUN)
        authorize_request(req, **authorization())

    def test_arbitrary_docker_fields_rejected(self):
        for field in ("command", "image", "mount", "docker_host", "script", "host_path"):
            with self.subTest(field=field), self.assertRaises(BrokerDenied):
                parse_request(message(**{field: "anything"}), now=NOW)

    def test_arbitrary_operation_rejected(self):
        for operation in ("docker_exec", "inspect", "run", "audit_osworld_network; rm -rf"):
            with self.subTest(operation=operation), self.assertRaises(BrokerDenied):
                parse_request(message(operation=operation), now=NOW)

    def test_duplicate_json_fields_rejected(self):
        with self.assertRaises(BrokerDenied):
            parse_request(b'{"run_id":"a","run_id":"b"}', now=NOW)

    def test_oversize_message_rejected(self):
        with self.assertRaises(BrokerDenied):
            parse_request(b" " * 1025, now=NOW)

    def test_non_dict_json_rejected(self):
        for raw in (b"[]", b"null", b"true", b'"text"'):
            with self.subTest(raw=raw), self.assertRaises(BrokerDenied):
                parse_request(raw, now=NOW)

    def test_bad_encoding_rejected(self):
        with self.assertRaises(BrokerDenied):
            parse_request(b"\xff", now=NOW)

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(BrokerDenied):
            parse_request(message().replace(str(NOW).encode(), b"NaN"), now=NOW)

    def test_bool_timestamp_rejected(self):
        with self.assertRaises(BrokerDenied):
            parse_request(message(issued_at=True), now=NOW)

    def test_stale_timestamp_rejected(self):
        with self.assertRaises(BrokerDenied):
            parse_request(message(issued_at=NOW - 31), now=NOW)

    def test_future_timestamp_rejected(self):
        with self.assertRaises(BrokerDenied):
            parse_request(message(issued_at=NOW + 6), now=NOW)

    def test_boundary_timestamps_accepted(self):
        for stamp in (NOW - 30, NOW + 5):
            with self.subTest(stamp=stamp):
                parse_request(message(issued_at=stamp), now=NOW)

    def test_invalid_identifier_rejected(self):
        for field, value in (("run_id", "A" * 32), ("container_id", "a" * 63), ("nonce", "invalid")):
            with self.subTest(field=field), self.assertRaises(BrokerDenied):
                parse_request(message(**{field: value}), now=NOW)

    def test_wrong_windows_identity_rejected_without_claiming(self):
        req = parse_request(message(), now=NOW)
        calls = []
        with self.assertRaises(BrokerDenied):
            authorize_request(req, **authorization(peer_sid="S-1-5-18", claim_nonce=lambda n: calls.append(n)))
        self.assertEqual(calls, [])

    def test_wrong_container_rejected(self):
        req = parse_request(message(), now=NOW)
        with self.assertRaises(BrokerDenied):
            authorize_request(req, **authorization(measured_container_id="d" * 64))

    def test_wrong_run_rejected(self):
        req = parse_request(message(), now=NOW)
        with self.assertRaises(BrokerDenied):
            authorize_request(req, **authorization(measured_run_id="d" * 32))

    def test_replayed_nonce_rejected(self):
        req = parse_request(message(), now=NOW)
        kwargs = authorization(claim_nonce=Nonces().claim)
        authorize_request(req, **kwargs)
        with self.assertRaises(BrokerDenied):
            authorize_request(req, **kwargs)

    def test_non_atomic_nonce_store_response_rejected(self):
        req = parse_request(message(), now=NOW)
        for value in (0, 1, None, "true", False):
            with self.subTest(value=value), self.assertRaises(BrokerDenied):
                authorize_request(req, **authorization(claim_nonce=lambda _: value))

    def test_nonce_store_exception_cannot_authorize(self):
        req = parse_request(message(), now=NOW)
        def unavailable(_):
            raise OSError("nonce store unavailable")
        with self.assertRaises(OSError):
            authorize_request(req, **authorization(claim_nonce=unavailable))

    def test_manual_object_construction_cannot_bypass_freshness(self):
        req = AuditRequest(RUN, CONTAINER, "c" * 32, NOW - 40)
        with self.assertRaises(BrokerDenied):
            authorize_request(req, **authorization())

    def test_untrusted_clock_rejected(self):
        with self.assertRaises(BrokerDenied):
            parse_request(message(), now=True)

    def test_sid_spoof_field_rejected(self):
        with self.assertRaises(BrokerDenied):
            parse_request(message(peer_sid=SID), now=NOW)

    def test_malformed_sid_rejected(self):
        req = parse_request(message(), now=NOW)
        with self.assertRaises(BrokerDenied):
            authorize_request(req, **authorization(peer_sid="ArdaNTM"))


if __name__ == "__main__":
    unittest.main()
