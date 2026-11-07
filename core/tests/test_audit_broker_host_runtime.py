"""F2.5 Windows SCM account and inactive IPC audit pipeline regressions.

Mock-only tests: no Windows users, Docker daemon, SCM services or private keys
are created, changed, queried or loaded from the host.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aura_core.osworld.audit_broker_protocol import BrokerDenied
from aura_core.osworld.audit_broker_receipt import DurableNonceStore
from aura_core.osworld.audit_broker_service import (
    BrokerServicePolicy, parse_service_policy,
)
from aura_core.osworld.audit_broker_topology import BrokerTopologyAudit
from aura_core.osworld import audit_broker_host_runtime as host
from aura_core.osworld import audit_broker_scm_identity as scm

SERVICE = "S-1-5-21-111-222-333-1002"
AUDITOR = "S-1-5-21-111-222-333-1001"
AGENT = "S-1-5-21-111-222-333-1003"

DENY = BrokerServicePolicy(SERVICE, AUDITOR, AGENT, "deny_only")
AUDIT = BrokerServicePolicy(SERVICE, AUDITOR, AGENT, "audit_only")


class WindowsSCMLogonTests(unittest.TestCase):
    def test_dedicated_windows_account_must_match_pinned_service_sid(self):
        scm.validate_registered_logon(
            policy=DENY, logon_name=r"ARDANTM\AuraBroker", resolved_sid=SERVICE,
        )

    def test_scm_account_sid_mismatch_denied(self):
        with self.assertRaises(BrokerDenied):
            scm.validate_registered_logon(
                policy=DENY, logon_name=r"ARDANTM\ardab", resolved_sid=AGENT,
            )

    def test_immutable_agent_auditor_broker_distinct(self):
        for sid in (AUDITOR, AGENT):
            with self.subTest(sid=sid), self.assertRaises(BrokerDenied):
                scm.validate_registered_logon(
                    policy=DENY, logon_name=r"ARDANTM\Other", resolved_sid=sid,
                )

    def test_builtin_service_accounts_rejected(self):
        for name in ("LocalSystem", r"NT AUTHORITY\SYSTEM",
                     r"NT AUTHORITY\LocalService",
                     r"NT AUTHORITY\NetworkService", "NetworkService"):
            with self.subTest(name=name), self.assertRaises(BrokerDenied):
                scm.validate_registered_logon(
                    policy=DENY, logon_name=name, resolved_sid=SERVICE,
                )

    def test_invalid_account_name_denied(self):
        for name in ("", " ", "bad\naccount", "bad\raccount"):
            with self.subTest(name=name), self.assertRaises(BrokerDenied):
                scm.validate_registered_logon(
                    policy=DENY, logon_name=name, resolved_sid=SERVICE,
                )

    def test_invalid_service_user_sid_denied(self):
        for sid in ("S-1-5-18", "S-1-5-32-544", "invalid", ""):
            with self.subTest(sid=sid), self.assertRaises(BrokerDenied):
                scm.validate_registered_logon(
                    policy=DENY, logon_name=r"ARDANTM\AuraBroker", resolved_sid=sid,
                )

    def test_scm_read_only_check_requires_windows(self):
        import os
        if os.name != "nt":
            with self.assertRaises(BrokerDenied):
                scm.verify_registered_service_account(DENY)

    def test_real_windows_scm_adapter_invokes_logon_check_and_stays_denied(self):
        filename = Path(__file__).resolve().parents[1] / "scripts" / "aura_docker_broker_service.py"
        code = filename.read_text("utf-8")
        self.assertIn("verify_registered_service_account(policy)", code)
        self.assertIn("serve_denied_request_once(policy)", code)
        self.assertNotIn("serve_signed_audit_once(", code)


class SealedHostAuditPipelineTests(unittest.TestCase):
    def test_shipped_service_config_cannot_enable_signed_audits(self):
        import json
        raw = json.dumps({
            "schema": "aura.osworld.broker-service.v1",
            "service_sid": SERVICE, "auditor_sid": AUDITOR,
            "agent_sid": AGENT, "mode": "audit_only",
        }).encode()
        with self.assertRaises(BrokerDenied):
            parse_service_policy(raw)

    def test_denied_service_cannot_construct_signing_pipeline(self):
        with (
            patch.object(host, "preflight_service", return_value=DENY),
            patch.object(host, "load_sealed_broker_key") as key_loader,
            patch.object(host, "DockerAuditBackend") as docker_factory,
        ):
            with self.assertRaises(BrokerDenied):
                host.build_sealed_audit_pipeline()
            key_loader.assert_not_called()
            docker_factory.assert_not_called()

    def test_unsigned_default_service_has_no_named_pipe_signing_handler(self):
        # The service handler is still the explicit deny_only implementation.
        from aura_core.osworld.audit_broker_service import blocked_handler, DENIED_RESPONSE
        self.assertEqual(blocked_handler(b"{}", AUDITOR), DENIED_RESPONSE)
        self.assertNotIn(b"ISOLATION_SIGNED", DENIED_RESPONSE)

    def test_sealed_broker_key_cannot_load_without_external_provisioning(self):
        with self.assertRaises(BrokerDenied):
            host.load_sealed_broker_key()

    def _pipeline(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        with (
            patch("aura_core.osworld.audit_broker_receipt._verify_private_state_path"),
            patch("aura_core.osworld.audit_broker_receipt._harden_state_file"),
        ):
            nonces = DurableNonceStore(Path(self.temp.name) / "nonces.sqlite3")
        topology = object.__new__(BrokerTopologyAudit)
        return host.BrokerAuditPipeline(
            policy=AUDIT, topology=topology,
            nonces=nonces, signer=Ed25519PrivateKey.generate(),
            identity_source=lambda: SERVICE,
        )

    def test_offline_audit_pipeline_is_broker_sid_only(self):
        obj = self._pipeline()
        with patch.object(host, "evaluate_broker_measurement",
                          return_value=b"signed-envelope") as evaluate:
            result = obj.handle(b"strict-request", AUDITOR)
            self.assertEqual(result, b"signed-envelope")
            kwargs = evaluate.call_args.kwargs
            self.assertEqual(kwargs["peer_sid"], AUDITOR)
            self.assertEqual(kwargs["auditor_sid"], AUDITOR)
            self.assertIs(kwargs["claim_nonce"].__self__, obj._nonces)
            self.assertIs(kwargs["topology"], obj._topology)

    def test_direct_agent_pid_cannot_use_signed_handler(self):
        obj = self._pipeline()
        obj._identity_source = lambda: AGENT
        with patch.object(host, "evaluate_broker_measurement") as evaluate:
            with self.assertRaises(BrokerDenied):
                obj.handle(b"strict-request", AUDITOR)
            evaluate.assert_not_called()

    def test_broker_signing_pipeline_cannot_be_built_in_deny_only_mode(self):
        with TemporaryDirectory() as directory:
            with (
                patch("aura_core.osworld.audit_broker_receipt._verify_private_state_path"),
                patch("aura_core.osworld.audit_broker_receipt._harden_state_file"),
            ):
                nonces = DurableNonceStore(Path(directory) / "nonce.sqlite3")
            with self.assertRaises(BrokerDenied):
                host.BrokerAuditPipeline(
                    policy=DENY, topology=object.__new__(BrokerTopologyAudit),
                    nonces=nonces, signer=Ed25519PrivateKey.generate(),
                    identity_source=lambda: SERVICE,
                )

    def test_native_pipe_dispatcher_uses_os_verified_auditor_sid(self):
        obj = self._pipeline()
        with (
            patch.object(host, "current_process_sid", return_value=SERVICE),
            patch.object(host, "serve_once") as dispatcher,
        ):
            host.serve_signed_audit_once(obj)
            kwargs = dispatcher.call_args.kwargs
            self.assertEqual(kwargs["auditor_sid"], AUDITOR)
            self.assertEqual(kwargs["expected_service_sid"], SERVICE)
            self.assertEqual(kwargs["forbidden_agent_sid"], AGENT)
            self.assertEqual(kwargs["handler"], obj.handle)

    def test_untrusted_pipe_dispatch_requires_broker_identity(self):
        obj = self._pipeline()
        with (
            patch.object(host, "current_process_sid", return_value=AGENT),
            patch.object(host, "serve_once") as dispatcher,
        ):
            with self.assertRaises(BrokerDenied):
                host.serve_signed_audit_once(obj)
            dispatcher.assert_not_called()

    def test_broker_handler_purpose_is_not_host_isolation_receipt(self):
        obj = self._pipeline()
        self.assertNotIn("ISOLATION_SIGNED", host.evaluate_broker_measurement.__doc__ or "")
        self.assertIsNotNone(obj._signer)


if __name__ == "__main__":
    unittest.main()
