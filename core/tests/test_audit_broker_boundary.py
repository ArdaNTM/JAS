"""F2.5 daemon-access and legacy-worker guardrail regressions.

No Docker daemon, Windows ACL, SCM, private key or local repo worktree is
modified. Test observations cannot be used as an authorization token.
"""
from __future__ import annotations

import asyncio
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

from aura_core.osworld.audit_broker_protocol import BrokerDenied
from aura_core.osworld import audit_broker_boundary as boundary
from aura_core.osworld import audit_broker_service as service

SERVICE = "S-1-5-21-111-222-333-1002"
AUDITOR = "S-1-5-21-111-222-333-1001"
AGENT = "S-1-5-21-111-222-333-1003"
POLICY = service.BrokerServicePolicy(SERVICE, AUDITOR, AGENT, "deny_only")


def observation(role, access, error=None, *, sid=None, endpoint=None):
    ids = {"broker": SERVICE, "auditor": AUDITOR, "agent": AGENT}
    return boundary.DaemonPipeObservation(
        role, ids[role] if sid is None else sid,
        boundary.DOCKER_DESKTOP_LINUX_PIPE if endpoint is None else endpoint,
        access, error,
    )


def valid_set():
    return (
        observation("agent", "denied", boundary.ACCESS_DENIED),
        observation("auditor", "denied", boundary.ACCESS_DENIED),
        observation("broker", "allowed"),
    )


class DaemonBoundaryContractTests(unittest.TestCase):
    def test_pinned_desktop_linux_pipe(self):
        self.assertEqual(
            boundary.DOCKER_DESKTOP_LINUX_PIPE,
            r"\\.\pipe\dockerDesktopLinuxEngine",
        )

    def test_three_separate_actual_tokens_with_decisive_access(self):
        boundary.validate_boundary_observations(valid_set(), policy=POLICY)

    def test_broker_denied_is_not_sufficient(self):
        checks = list(valid_set())
        checks[-1] = observation("broker", "denied", boundary.ACCESS_DENIED)
        with self.assertRaises(BrokerDenied):
            boundary.validate_boundary_observations(tuple(checks), policy=POLICY)

    def test_unavailable_agent_daemon_is_not_access_denial(self):
        checks = list(valid_set())
        checks[0] = observation("agent", "unavailable", boundary.PIPE_MISSING)
        with self.assertRaises(BrokerDenied):
            boundary.validate_boundary_observations(tuple(checks), policy=POLICY)

    def test_busy_auditor_pipe_is_not_access_denial(self):
        checks = list(valid_set())
        checks[1] = observation("auditor", "unavailable", boundary.PIPE_BUSY)
        with self.assertRaises(BrokerDenied):
            boundary.validate_boundary_observations(tuple(checks), policy=POLICY)

    def test_agent_cannot_have_daemon_access(self):
        checks = list(valid_set())
        checks[0] = observation("agent", "allowed")
        with self.assertRaises(BrokerDenied):
            boundary.validate_boundary_observations(tuple(checks), policy=POLICY)

    def test_auditor_cannot_have_daemon_access(self):
        checks = list(valid_set())
        checks[1] = observation("auditor", "allowed")
        with self.assertRaises(BrokerDenied):
            boundary.validate_boundary_observations(tuple(checks), policy=POLICY)

    def test_observations_must_be_distinct_roles(self):
        checks = list(valid_set())
        checks[1] = checks[0]
        with self.assertRaises(BrokerDenied):
            boundary.validate_boundary_observations(tuple(checks), policy=POLICY)

    def test_wrong_token_sid_is_not_validated(self):
        checks = list(valid_set())
        checks[1] = observation("auditor", "denied", boundary.ACCESS_DENIED, sid=AGENT)
        with self.assertRaises(BrokerDenied):
            boundary.validate_boundary_observations(tuple(checks), policy=POLICY)

    def test_mismatched_pipe_cannot_prove_separation(self):
        checks = list(valid_set())
        checks[1] = observation("auditor", "denied", boundary.ACCESS_DENIED,
                                endpoint=r"\\.\pipe\unrelated")
        with self.assertRaises(BrokerDenied):
            boundary.validate_boundary_observations(tuple(checks), policy=POLICY)

    def test_fake_access_denied_without_windows_error_rejected(self):
        checks = list(valid_set())
        checks[0] = observation("agent", "denied", boundary.PIPE_MISSING)
        with self.assertRaises(BrokerDenied):
            boundary.validate_boundary_observations(tuple(checks), policy=POLICY)

    def test_invalid_windows_error_types_are_rejected(self):
        checks = list(valid_set())
        checks[0] = observation("agent", "denied", True)
        with self.assertRaises(BrokerDenied):
            boundary.validate_boundary_observations(tuple(checks), policy=POLICY)

    def test_actual_os_sid_checked_before_pinned_pipe(self):
        probe = unittest.mock.Mock(return_value=("denied", boundary.ACCESS_DENIED))
        with self.assertRaises(BrokerDenied):
            boundary.inspect_current_principal(
                role="agent", expected_sid=AGENT,
                sid_source=lambda: SERVICE, access_probe=probe,
            )
        probe.assert_not_called()

    def test_observation_cannot_make_agent_access_safe(self):
        with self.assertRaises(BrokerDenied):
            boundary.require_no_agent_daemon_access(
                agent_sid=AGENT,
                sid_source=lambda: AGENT,
                access_probe=lambda: ("allowed", None),
            )

    def test_only_access_denied_proves_local_agent_denial(self):
        boundary.require_no_agent_daemon_access(
            agent_sid=AGENT,
            sid_source=lambda: AGENT,
            access_probe=lambda: ("denied", boundary.ACCESS_DENIED),
        )

    def test_no_untrusted_role_parameter(self):
        with self.assertRaises(BrokerDenied):
            boundary.inspect_current_principal(
                role="local_owner", expected_sid=AGENT,
                sid_source=lambda: AGENT, access_probe=lambda: ("allowed", None),
            )

    def test_unavailable_result_is_rejected_as_agent_boundary(self):
        with self.assertRaises(BrokerDenied):
            boundary.require_no_agent_daemon_access(
                agent_sid=AGENT,
                sid_source=lambda: AGENT,
                access_probe=lambda: ("unavailable", boundary.PIPE_MISSING),
            )

    def test_windows_only_native_probe(self):
        import os
        if os.name != "nt":
            with self.assertRaises(BrokerDenied):
                boundary._native_pipe_access()


class BrokerServiceDaemonPreflightTests(unittest.TestCase):
    def test_broker_needs_real_daemon_access_before_start(self):
        def fake_obs(**kwargs):
            self.assertEqual(kwargs, {"role": "broker", "expected_sid": SERVICE})
            return observation("broker", "denied", boundary.ACCESS_DENIED)
        with (
            patch.object(service, "verify_trusted_runtime"),
            patch.object(service, "load_service_policy", return_value=POLICY),
            patch.object(service, "current_process_sid", return_value=SERVICE),
            patch.object(boundary, "inspect_current_principal", side_effect=fake_obs),
        ):
            with self.assertRaises(BrokerDenied):
                service.preflight_service()

    def test_broker_identity_and_daemon_preflight_would_allow_deny_only(self):
        with (
            patch.object(service, "verify_trusted_runtime"),
            patch.object(service, "load_service_policy", return_value=POLICY),
            patch.object(service, "current_process_sid", return_value=SERVICE),
            patch.object(boundary, "inspect_current_principal",
                         return_value=observation("broker", "allowed")),
        ):
            result = service.preflight_service()
            self.assertEqual(result.mode, "deny_only")

    def test_wrong_broker_token_skips_engine_probe(self):
        with (
            patch.object(service, "verify_trusted_runtime"),
            patch.object(service, "load_service_policy", return_value=POLICY),
            patch.object(service, "current_process_sid", return_value=AGENT),
            patch.object(boundary, "inspect_current_principal") as observed,
        ):
            with self.assertRaises(BrokerDenied):
                service.preflight_service()
            observed.assert_not_called()


class DaemonBoundaryCLIAndRunnerTests(unittest.TestCase):
    @staticmethod
    def _load_script(name):
        path = Path(__file__).resolve().parents[1] / "scripts" / (name + ".py")
        spec = importlib.util.spec_from_file_location("test_f25_" + name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_operator_probe_says_observation_not_signed_receipt(self):
        script = self._load_script("inspect_osworld_docker_boundary")
        buffer = io.StringIO()
        with (
            patch.object(script, "inspect_current_principal",
                         return_value=observation("broker", "allowed")),
            redirect_stdout(buffer),
        ):
            self.assertEqual(script.main(["--role", "broker",
                                          "--expected-sid", SERVICE]), 0)
        result = json.loads(buffer.getvalue())
        self.assertEqual(result["status"], "OBSERVATION_ONLY")
        self.assertIs(result["signed"], False)
        self.assertNotIn("ISOLATION_SIGNED", buffer.getvalue())

    def test_operator_probe_rejects_missing_daemon(self):
        script = self._load_script("inspect_osworld_docker_boundary")
        buffer = io.StringIO()
        with (
            patch.object(script, "inspect_current_principal",
                         return_value=observation("agent", "unavailable",
                                                  boundary.PIPE_MISSING)),
            redirect_stdout(buffer),
        ):
            self.assertEqual(script.main(["--role", "agent",
                                          "--expected-sid", AGENT]), 2)
        self.assertEqual(json.loads(buffer.getvalue())["status"], "BOUNDARY_BLOCKED")

    def test_live_runner_blocks_legacy_agent_docker_before_spawning(self):
        runner = self._load_script("run_osworld_v2_live")
        args = SimpleNamespace(allow_real_vm=True, smoke=False)
        with patch.object(runner, "OSWorldSubprocessVM") as bridge:
            with self.assertRaisesRegex(PermissionError, "broker-owned lifecycle"):
                asyncio.run(runner.run(args))
            bridge.assert_not_called()

    def test_smoke_runner_remains_gated_by_pinned_release(self):
        runner = self._load_script("run_osworld_v2_live")
        args = SimpleNamespace(allow_real_vm=True, smoke=True,
                               upstream=Path("definitely-missing-osworld"),
                               upstream_commit="f" * 40)
        with self.assertRaises(PermissionError):
            asyncio.run(runner.run(args))

    def test_agent_consent_remains_required(self):
        runner = self._load_script("run_osworld_v2_live")
        with self.assertRaisesRegex(PermissionError, "--allow-real-vm"):
            asyncio.run(runner.run(SimpleNamespace(allow_real_vm=False)))


if __name__ == "__main__":
    unittest.main()
