"""F2.5 regression: broker-owned worker cannot be started by an agent.

Fake VM factories, immutable D: pins and token sources are used. These tests
do not create a Windows service, spawn a Docker process, or sign receipts.
"""
from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from aura_core.osworld.audit_broker_protocol import BrokerDenied
from aura_core.osworld.audit_broker_service import BrokerServicePolicy
from aura_core.osworld import audit_broker_vm_executor as vm
from aura_core.osworld.isolation import BootIdentity, IMAGE

SERVICE = "S-1-5-21-111-222-333-1002"
AUDITOR = "S-1-5-21-111-222-333-1001"
AGENT = "S-1-5-21-111-222-333-1003"
POLICY = BrokerServicePolicy(SERVICE, AUDITOR, AGENT, "deny_only")
BOOT = BootIdentity(
    "a" * 64, "b" * 64, "c" * 64, IMAGE, "d" * 64, "e" * 64,
)


class FakeVM:
    def __init__(self, boot=BOOT):
        self.boot = boot
        self.closed = False

    def close(self):
        self.closed = True


class BrokerOwnedVMExecutorTests(unittest.TestCase):
    def setUp(self):
        self.call_log = []
        self.factory_vm = FakeVM()
        def factory(**kwargs):
            self.call_log.append(kwargs)
            return self.factory_vm
        self.verify_vm = Mock()
        self.verify_service = Mock(return_value=POLICY)
        self.identity = Mock(return_value=SERVICE)
        self.executor = vm.BrokerOwnedVMExecutor(
            policy=POLICY, runtime_preflight=self.verify_vm,
            service_preflight=self.verify_service,
            identity_source=self.identity, factory=factory,
        )

    def test_broker_token_can_start_fixed_worker_without_parameters(self):
        boot = self.executor.start()
        self.assertEqual(boot, BOOT)
        self.assertEqual(len(self.call_log), 1)
        self.assertEqual(self.call_log[0], {
            "upstream": vm.PINNED_UPSTREAM,
            "worker": vm.PINNED_WORKER,
            "boot_timeout": 900,
            "assets": None,
            "force_no_kvm": False,
            "website_suffix": None,
        })
        self.verify_vm.assert_called_once()
        self.verify_service.assert_called()

    def test_caller_cannot_supply_arbitrary_worker_or_docker_options(self):
        with self.assertRaises(TypeError):
            self.executor.start(worker=Path("untrusted_worker.py"))
        with self.assertRaises(TypeError):
            self.executor.start(docker_host="tcp://127.0.0.1:2375")
        self.assertEqual(self.call_log, [])

    def test_agent_token_denied_before_code_or_process_use(self):
        self.identity.return_value = AGENT
        with self.assertRaises(BrokerDenied):
            self.executor.start()
        self.assertEqual(self.call_log, [])
        self.verify_vm.assert_not_called()

    def test_auditor_token_denied_before_spawn(self):
        self.identity.return_value = AUDITOR
        with self.assertRaises(BrokerDenied):
            self.executor.start()
        self.verify_vm.assert_not_called()

    def test_changed_service_policy_denied_before_worker(self):
        self.verify_service.return_value = BrokerServicePolicy(
            SERVICE, AUDITOR, AGENT, "live",
        )
        with self.assertRaises(BrokerDenied):
            self.executor.start()
        self.assertEqual(self.call_log, [])

    def test_missing_sealed_runtime_denied_before_worker(self):
        self.verify_vm.side_effect = BrokerDenied("Agent writable worker path")
        with self.assertRaises(BrokerDenied):
            self.executor.start()
        self.assertEqual(self.call_log, [])

    def test_only_one_vm_can_exist_per_broker_host(self):
        self.executor.start()
        with self.assertRaises(BrokerDenied):
            self.executor.start()
        self.assertEqual(len(self.call_log), 1)

    def test_stop_closes_broker_owned_worker(self):
        self.executor.start()
        self.executor.stop()
        self.assertTrue(self.factory_vm.closed)

    def test_stop_checks_same_service_token(self):
        self.executor.start()
        self.identity.return_value = AGENT
        with self.assertRaises(BrokerDenied):
            self.executor.stop()
        self.assertFalse(self.factory_vm.closed)
        self.identity.return_value = SERVICE
        self.executor.stop()
        self.assertTrue(self.factory_vm.closed)

    def test_invalid_vm_identity_closes_and_denies(self):
        self.factory_vm.boot = None
        with self.assertRaises(BrokerDenied):
            self.executor.start()
        self.assertTrue(self.factory_vm.closed)

    def test_no_guest_action_without_individual_owner_approval(self):
        self.assertFalse(hasattr(self.executor, "step_action"))
        self.assertFalse(hasattr(self.executor, "reset"))
        self.assertFalse(hasattr(self.executor, "evaluate"))
        self.assertFalse(hasattr(self.executor, "run_docker"))

    def test_sealed_vm_root_is_not_agent_checkout(self):
        self.assertIn("DockerBroker", str(vm.PINNED_WORKER))
        self.assertEqual(vm.PINNED_UPSTREAM, Path(r"D:\AURA\OSWorld-V2"))
        self.assertNotIn("JAS-real-world-test", str(vm.PINNED_WORKER))
        self.assertNotIn("JAS-real-world-test", str(vm.PINNED_PYTHON))

    def test_non_windows_default_runtime_cannot_pass(self):
        import os
        if os.name != "nt":
            with self.assertRaises(BrokerDenied):
                vm.verify_sealed_vm_runtime()

    def test_policy_is_deny_only_not_live_switch(self):
        with self.assertRaises(BrokerDenied):
            vm.BrokerOwnedVMExecutor(
                policy=BrokerServicePolicy(SERVICE, AUDITOR, AGENT, "live")
            )


if __name__ == "__main__":
    unittest.main()
