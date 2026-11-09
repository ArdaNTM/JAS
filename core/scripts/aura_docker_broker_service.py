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
            try:
                policy = preflight_ubuntu_deny_only_service()
                # SCM registration must match this real process token. A
                # policy JSON SID by itself is not Windows account evidence.
                from aura_core.osworld.audit_broker_scm_identity import (
                    verify_registered_service_account,
                )
                verify_registered_service_account(policy)
            except Exception:
                return
            # An SCM stop must remain responsive even if ConnectNamedPipe
            # blocks. Only one deny-only request is handled in this stage.
            from threading import Thread
            def one_request():
                try:
                    serve_denied_request_once(policy)
                finally:
                    win32event.SetEvent(self._stop_event)
            Thread(target=one_request, name="aura-broker-deny-only", daemon=True).start()
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
