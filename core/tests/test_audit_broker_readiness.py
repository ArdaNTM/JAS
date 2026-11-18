"""Stage F2.6 fail-closed per-token readiness tests (offline only)."""
from __future__ import annotations

import contextlib
from dataclasses import asdict
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from aura_core.osworld.audit_broker_protocol import BrokerDenied
from aura_core.osworld.audit_broker_boundary import ACCESS_DENIED, PIPE_MISSING
from aura_core.osworld import audit_broker_readiness as readiness

BROKER = "S-1-5-21-111-222-333-1002"
AUDITOR = "S-1-5-21-111-222-333-1001"
AGENT = "S-1-5-21-111-222-333-1003"


def inspect(role, sid, access, errno, *, check=None):
    return readiness.inspect_role_readiness(
        role=role, expected_sid=sid,
        sid_source=lambda: sid,
        access_probe=lambda: (access, errno),
        broker_prerequisites=check,
    )


class PerTokenF26ReadinessTests(unittest.TestCase):
    def test_agent_access_denied_remains_unsigned(self):
        result = inspect("agent", AGENT, "denied", ACCESS_DENIED)
        self.assertEqual(result.role, "agent")
        self.assertEqual(result.daemon_access, "denied")
        self.assertIs(result.signed, False)
        self.assertEqual(result.status, "OBSERVATION_ONLY")
        self.assertFalse(result.service_identity_checked)

    def test_auditor_access_denied_remains_unsigned(self):
        result = inspect("auditor", AUDITOR, "denied", ACCESS_DENIED)
        self.assertIs(result.signed, False)
        self.assertFalse(result.sealed_runtime_checked)

    def test_broker_allowed_requires_service_and_sealed_runtime_check(self):
        checked = Mock()
        result = inspect("broker", BROKER, "allowed", None, check=checked)
        checked.assert_called_once_with(BROKER)
        self.assertIs(result.signed, False)
        self.assertTrue(result.service_identity_checked)
        self.assertTrue(result.sealed_runtime_checked)

    def test_agent_allowed_is_denied(self):
        with self.assertRaises(BrokerDenied):
            inspect("agent", AGENT, "allowed", None)

    def test_auditor_allowed_is_denied(self):
        with self.assertRaises(BrokerDenied):
            inspect("auditor", AUDITOR, "allowed", None)

    def test_broker_denied_is_denied(self):
        with self.assertRaises(BrokerDenied):
            inspect("broker", BROKER, "denied", ACCESS_DENIED, check=Mock())

    def test_unavailable_engine_cannot_prove_separation(self):
        for role, sid in (("agent", AGENT), ("auditor", AUDITOR), ("broker", BROKER)):
            with self.subTest(role=role), self.assertRaises(BrokerDenied):
                inspect(role, sid, "unavailable", PIPE_MISSING, check=Mock())

    def test_wrong_current_sid_refused_before_pipe(self):
        with self.assertRaises(BrokerDenied):
            readiness.inspect_role_readiness(
                role="auditor", expected_sid=AUDITOR,
                sid_source=lambda: AGENT,
                access_probe=Mock(side_effect=AssertionError("must not run")),
            )

    def test_arbitrary_role_denied(self):
        for role in ("owner", "root", "local_owner", "", "docker-admin"):
            with self.subTest(role=role), self.assertRaises(BrokerDenied):
                inspect(role, AGENT, "denied", ACCESS_DENIED)

    def test_broker_preflight_exception_fails_closed(self):
        checker = Mock(side_effect=BrokerDenied("Unsealed binary"))
        with self.assertRaises(BrokerDenied):
            inspect("broker", BROKER, "allowed", None, check=checker)
        checker.assert_called_once()

    def test_broker_checker_not_called_by_agent(self):
        checker = Mock(side_effect=AssertionError("broker-only"))
        inspect("agent", AGENT, "denied", ACCESS_DENIED, check=checker)
        checker.assert_not_called()

    def test_observation_never_has_signing_evidence(self):
        result = asdict(inspect("agent", AGENT, "denied", ACCESS_DENIED))
        self.assertNotIn("signature_b64", result)
        self.assertNotIn("ISOLATION_SIGNED", json.dumps(result))
        self.assertNotIn("receipt", result)

    def test_cannot_construct_fake_signed_readiness(self):
        with self.assertRaises(BrokerDenied):
            readiness.HostReadinessObservation(
                "agent", AGENT, "denied", False, False, True,
            )

    def test_cannot_construct_fake_success_status(self):
        with self.assertRaises(BrokerDenied):
            readiness.HostReadinessObservation(
                "agent", AGENT, "denied", False, False, False, "ISOLATION_SIGNED",
            )

    def test_broker_requires_deny_only_at_activation_check(self):
        from aura_core.osworld.audit_broker_service import BrokerServicePolicy
        wrong = BrokerServicePolicy(BROKER, AUDITOR, AGENT, "audit_only")
        with (
            patch.object(readiness, "preflight_service", return_value=wrong),
            patch.object(readiness, "validate_service_identity"),
            patch.object(readiness, "verify_registered_service_account") as scm,
        ):
            with self.assertRaises(BrokerDenied):
                readiness._check_broker_prerequisites(BROKER)
            scm.assert_not_called()

    def test_broker_scm_and_runtime_only_after_policy(self):
        from aura_core.osworld.audit_broker_service import BrokerServicePolicy
        valid = BrokerServicePolicy(BROKER, AUDITOR, AGENT, "deny_only")
        with (
            patch.object(readiness, "preflight_service", return_value=valid),
            patch.object(readiness, "validate_service_identity") as validator,
            patch.object(readiness, "verify_registered_service_account") as scm,
            patch.object(readiness, "verify_sealed_vm_runtime") as sealed,
        ):
            readiness._check_broker_prerequisites(BROKER)
            validator.assert_called_once_with(valid, actual_sid=BROKER)
            scm.assert_called_once_with(valid)
            sealed.assert_called_once()


class ReadinessCLIF26Tests(unittest.TestCase):
    def setUp(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "preflight_osworld_f26.py"
        spec = importlib.util.spec_from_file_location("test_osworld_f26_preflight", script)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        self.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cli)

    def test_cli_success_remains_only_observation(self):
        observation = readiness.HostReadinessObservation(
            "agent", AGENT, "denied", False, False,
        )
        buffer = io.StringIO()
        with (
            patch.object(self.cli, "inspect_role_readiness", return_value=observation),
            contextlib.redirect_stdout(buffer),
        ):
            rc = self.cli.main(["--role", "agent", "--expected-sid", AGENT])
        self.assertEqual(rc, 0)
        obj = json.loads(buffer.getvalue())
        self.assertIs(obj["signed"], False)
        self.assertEqual(obj["status"], "OBSERVATION_ONLY")
        self.assertIn("cannot authorize", obj["disclaimer"].lower())

    def test_cli_failure_emits_blocked_and_no_secret(self):
        buffer = io.StringIO()
        with (
            patch.object(self.cli, "inspect_role_readiness",
                         side_effect=BrokerDenied("broker-ed25519.pem contents here")),
            contextlib.redirect_stdout(buffer),
        ):
            rc = self.cli.main(["--role", "broker", "--expected-sid", BROKER])
        self.assertEqual(rc, 2)
        obj = json.loads(buffer.getvalue())
        self.assertEqual(obj["status"], "ISOLATION_BLOCKED")
        self.assertIs(obj["signed"], False)
        self.assertNotIn("pem contents", buffer.getvalue())

    def test_cli_never_imports_signer_or_enables_service(self):
        source = (Path(__file__).resolve().parents[1] / "scripts" /
                  "preflight_osworld_f26.py").read_text(encoding="utf-8")
        self.assertNotIn("sign_measurement(", source)
        self.assertNotIn("ISOLATION_SIGNED", source)
        self.assertNotIn("update_parental", source)
        self.assertNotIn("create_service", source)


if __name__ == "__main__":
    unittest.main()
