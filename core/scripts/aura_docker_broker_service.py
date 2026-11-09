"""Windows SCM adapter for the staged Ubuntu-targeted deny-only broker.

Do NOT register/start this from the writable AURA checkout. Package a pinned,
ACL-protected Python runtime, source tree and policy into
D:\AURA\Trust\DockerBroker\bin before any explicit service installation.
No Docker permission is provisioned. Actual service-account configuration
is an independent administrator operation, never performed by an agent.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

from aura_core.osworld.audit_broker_protocol import BrokerDenied
from aura_core.osworld.audit_broker_service import (
    BIN_ROOT, SERVICE_NAME, POLICY_PATH, preflight_ubuntu_deny_only_service,
    serve_denied_request_once, verify_trusted_runtime,
)

if os.name == "nt":
    import win32event
    import win32service
    import win32serviceutil

    class AuraDockerBrokerService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = "AURA OSWorld Trusted Docker Audit Broker (deny-only)"
        _svc_description_ = (
            "Stage F2.1: independently identified host broker IPC; "
            "no Docker operations or signatures enabled"
        )

        def __init__(self, args):
            super().__init__(args)
            self._stop_event = win32event.CreateEvent(None, 0, 0, None)

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self._stop_event)

        def SvcDoRun(self):
            # Ubuntu deny-only requires real SID and sealed runtime, not a
            # Windows Docker Desktop pipe. Fail before creating any IPC.
            # assertion fails. Catching here does not authorize continuation.
            # Deny-only is the default. A signed F2.7 operator approval is
            # mandatory before constructing a live SSH transport. Failure
            # never falls back to an unauthenticated live mode.
            try:
                from aura_core.osworld.audit_broker_scm_identity import (
                    verify_registered_service_account,
                )
                try:
                    policy = preflight_ubuntu_deny_only_service()
                except BrokerDenied:
                    from aura_core.osworld.audit_broker_f27_activation import (
                        load_operator_approved_activation,
                    )
                    from aura_core.osworld.audit_broker_f27_bridge import (
                        serve_approved_request_once,
                    )
                    approved = load_operator_approved_activation(verify_inventory=True)
                    verify_registered_service_account(approved.policy)
                    operation = lambda: serve_approved_request_once(approved)
                else:
                    verify_registered_service_account(policy)
                    operation = lambda: serve_denied_request_once(policy)
            except Exception:
                return
            # A single authenticated message, service stop stays responsive.
            # No unsigned report is ever elevated to ISOLATION_SIGNED.
            from threading import Thread
            def one_request():
                try:
                    operation()
                finally:
                    win32event.SetEvent(self._stop_event)
            Thread(target=one_request, name="aura-broker-one-shot", daemon=True).start()
            win32event.WaitForSingleObject(self._stop_event, win32event.INFINITE)


def main() -> int:
    if os.name != "nt":
        raise BrokerDenied("Windows SCM broker is Windows-only")
    script = Path(__file__).resolve(strict=True)
    if not script.is_relative_to(BIN_ROOT):
        raise BrokerDenied("Broker SCM module cannot run from the AURA checkout")
    verify_trusted_runtime(
        source_file=script, python_executable=Path(sys.executable),
    )
    if not POLICY_PATH.is_file():
        raise BrokerDenied("Protected broker service policy has not been provisioned")
    win32serviceutil.HandleCommandLine(AuraDockerBrokerService)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
