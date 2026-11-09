"""Stage F2.1 service account, policy and fail-closed launch unit tests."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from aura_core.osworld.audit_broker_protocol import BrokerDenied
from aura_core.osworld import audit_broker_service as service

SERVICE = "S-1-5-21-111-222-333-1002"
AUDITOR = "S-1-5-21-111-222-333-1001"
AGENT = "S-1-5-21-111-222-333-1003"


def policy(**overrides):
    doc = {
        "schema": service.POLICY_SCHEMA,
        "service_sid": SERVICE,
        "auditor_sid": AUDITOR,
        "agent_sid": AGENT,
        "mode": "deny_only",
    }
    doc.update(overrides)
    return json.dumps(doc).encode("ascii")


class BrokerServicePolicyTests(unittest.TestCase):
    def test_valid_separate_service_account(self):
        p = service.parse_service_policy(policy())
        service.validate_service_identity(p, actual_sid=SERVICE)
        self.assertEqual(p.mode, "deny_only")

    def test_only_deny_only_mode_allowed(self):
        for mode in ("live", "docker", "audit", "", None):
            with self.subTest(mode=mode), self.assertRaises(BrokerDenied):
                service.parse_service_policy(policy(mode=mode))

    def test_agent_identity_same_as_service_rejected(self):
        with self.assertRaises(BrokerDenied):
            service.parse_service_policy(policy(agent_sid=SERVICE))

    def test_auditor_identity_same_as_service_rejected(self):
        with self.assertRaises(BrokerDenied):
            service.parse_service_policy(policy(auditor_sid=SERVICE))

    def test_agent_and_auditor_identity_same_rejected(self):
        with self.assertRaises(BrokerDenied):
            service.parse_service_policy(policy(agent_sid=AUDITOR))

    def test_malformed_sid_rejected(self):
        for sid in ("S-1-5-18", "S-1-5-32-544", "ardantm\\owner", "S-1-5-21-1"):
            with self.subTest(sid=sid), self.assertRaises(BrokerDenied):
                service.parse_service_policy(policy(service_sid=sid))

    def test_wrong_actual_service_sid_rejected(self):
        with self.assertRaises(BrokerDenied):
            service.validate_service_identity(
                service.parse_service_policy(policy()), actual_sid=AGENT
            )

    def test_service_policy_extra_fields_rejected(self):
        with self.assertRaises(BrokerDenied):
            service.parse_service_policy(policy(allow_docker=True))

    def test_duplicate_policy_keys_rejected(self):
        data = policy().replace(b'"mode": "deny_only"', b'"mode": "deny_only", "mode": "live"')
        with self.assertRaises(BrokerDenied):
            service.parse_service_policy(data)

    def test_non_json_and_oversize_denied(self):
        for raw in (b"{", b"[]", b"null", b"\xff", b"x" * 2049):
            with self.subTest(raw=raw[:12]), self.assertRaises(BrokerDenied):
                service.parse_service_policy(raw)

    def test_unexpected_schema_rejected(self):
        with self.assertRaises(BrokerDenied):
            service.parse_service_policy(policy(schema="other"))

    def test_deny_handler_never_signs(self):
        self.assertEqual(
            service.blocked_handler(b'{"operation":"audit"}', AUDITOR),
            service.DENIED_RESPONSE,
        )
        self.assertNotIn(b"ISOLATION_SIGNED", service.DENIED_RESPONSE)

    def test_mismatched_service_refuses_pipe_before_open(self):
        p = service.parse_service_policy(policy())
        with (
            patch.object(service, "current_process_sid", return_value=AGENT),
            patch("aura_core.osworld.audit_broker_windows.serve_once") as pipe,
        ):
            with self.assertRaises(BrokerDenied):
                service.serve_denied_request_once(p)
            pipe.assert_not_called()

    def test_trusted_service_uses_pinned_pipe_and_deny_handler(self):
        p = service.parse_service_policy(policy())
        with (
            patch.object(service, "current_process_sid", return_value=SERVICE),
            patch("aura_core.osworld.audit_broker_windows.serve_once") as pipe,
        ):
            service.serve_denied_request_once(p)
            kwargs = pipe.call_args.kwargs
            self.assertEqual(kwargs["auditor_sid"], AUDITOR)
            self.assertEqual(kwargs["expected_service_sid"], SERVICE)
            self.assertEqual(kwargs["forbidden_agent_sid"], AGENT)
            self.assertIs(kwargs["handler"], service.blocked_handler)


class UbuntuDenyOnlySCMPreflightTests(unittest.TestCase):
    """Offline SCM checks; never open a Docker pipe or contact Ubuntu."""

    def test_ubuntu_deny_only_sealed_sid_without_desktop_daemon(self):
        approved = service.parse_service_policy(policy())
        with (
            patch.object(service, "verify_trusted_runtime") as sealed,
            patch.object(service, "load_service_policy", return_value=approved),
            patch.object(service, "current_process_sid", return_value=SERVICE),
            patch("aura_core.osworld.audit_broker_boundary.inspect_current_principal")
            as docker_probe,
        ):
            observed = service.preflight_ubuntu_deny_only_service()
            self.assertIs(observed, approved)
            sealed.assert_called_once()
            docker_probe.assert_not_called()

    def test_ubuntu_deny_only_wrong_runtime_token_refused(self):
        approved = service.parse_service_policy(policy())
        with (
            patch.object(service, "verify_trusted_runtime"),
            patch.object(service, "load_service_policy", return_value=approved),
            patch.object(service, "current_process_sid", return_value=AGENT),
            patch("aura_core.osworld.audit_broker_boundary.inspect_current_principal")
            as docker_probe,
        ):
            with self.assertRaises(BrokerDenied):
                service.preflight_ubuntu_deny_only_service()
            docker_probe.assert_not_called()

    def test_fabricated_audit_only_dataclass_cannot_start_ubuntu_scm(self):
        from dataclasses import replace
        approved = replace(service.parse_service_policy(policy()), mode="audit_only")
        with (
            patch.object(service, "verify_trusted_runtime"),
            patch.object(service, "load_service_policy", return_value=approved),
            patch.object(service, "current_process_sid") as identity,
        ):
            with self.assertRaises(BrokerDenied):
                service.preflight_ubuntu_deny_only_service()
            identity.assert_not_called()

    def test_missing_sealed_runtime_fails_before_policy_and_scm(self):
        with (
            patch.object(service, "verify_trusted_runtime",
                         side_effect=BrokerDenied("unsealed")) as sealed,
            patch.object(service, "load_service_policy") as policy_loader,
        ):
            with self.assertRaises(BrokerDenied):
                service.preflight_ubuntu_deny_only_service()
            sealed.assert_called_once()
            policy_loader.assert_not_called()

    def test_scm_adapter_explicitly_uses_ubuntu_deny_only_preflight(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / "scripts" /
                  "aura_docker_broker_service.py").read_text("utf-8")
        self.assertIn("policy = preflight_ubuntu_deny_only_service()", source)
        self.assertIn("verify_registered_service_account(policy)", source)
        self.assertIn("serve_denied_request_once(policy)", source)
        self.assertNotIn("UbuntuBrokerSshTransport(", source)


if __name__ == "__main__":
    unittest.main()
