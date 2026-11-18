"""F2.5 broker-owned OSWorld worker lifecycle — operator-only foundation.

Runs the existing *pinned* OSWorld 3.12 subprocess under the current Windows
broker service token (Windows child processes inherit that token), never
under the AURA agent token. No untrusted IPC command can invoke this class.
No guest actions/steps, evaluator, Docker CLI flags, arbitrary paths, tokens,
owner approvals, or file transfers are exposed here. Activation requires an
independent owner-authorized lifecycle transport in a later review.

The backend remains deny-only in the shipped Windows SCM service. Code
provides a guarded implementation for a separately provisioned service; it
does not create users, change groups, install services or start a real VM.
"""
from __future__ import annotations

import os
from pathlib import Path
import threading
from typing import Callable, Protocol

from .audit_broker_protocol import BrokerDenied
from .audit_broker_service import (
    BIN_ROOT, BrokerServicePolicy, preflight_service,
    validate_service_identity,
)
from .audit_broker_windows import current_process_sid
from .isolation import BootIdentity
from .runtime_bridge import OSWorldSubprocessVM

# Fixed service-owned, ACL-protected installation paths.
# The mutable agent checkout and its Python environment are NOT supported.
PINNED_CORE = BIN_ROOT / "core"
PINNED_WORKER = PINNED_CORE / "scripts" / "osworld_secure_worker.py"
PINNED_UPSTREAM = Path(r"D:\AURA\OSWorld-V2")
PINNED_PYTHON = PINNED_UPSTREAM / ".venv" / "Scripts" / "python.exe"
PINNED_DISK = PINNED_UPSTREAM / "docker_vm_data" / "osworld-v2-ubuntu-x86.qcow2"


class _VM(Protocol):
    boot: BootIdentity | None
    def close(self) -> None: ...


def _sealed_host_path(path: Path, *, is_dir: bool) -> None:
    """Fail closed when the code, interpreter or disk can be swapped by agent."""
    if not path.is_absolute() or path.is_symlink():
        raise BrokerDenied("Pinned OSWorld executable, disk or directory is redirected")
    if not (path.is_dir() if is_dir else path.is_file()):
        raise BrokerDenied("Pinned broker-owned OSWorld asset is missing")
    if path.resolve(strict=True) != path.absolute():
        raise BrokerDenied("OSWorld asset traverses an untrusted filesystem link")
    from aura_core.evolution.windows_owner_storage import require_private_acl
    require_private_acl(path)


def verify_sealed_vm_runtime() -> None:
    """Validate actual D: trust boundary, no file/ACL mutation."""
    if os.name != "nt":
        raise BrokerDenied("A dedicated Windows broker service is required")
    for path in (
        BIN_ROOT, PINNED_CORE, PINNED_CORE / "scripts", PINNED_UPSTREAM,
        PINNED_UPSTREAM / ".venv", PINNED_UPSTREAM / ".venv" / "Scripts",
        PINNED_DISK.parent,
    ):
        _sealed_host_path(path, is_dir=True)
    for path in (PINNED_WORKER, PINNED_PYTHON, PINNED_DISK):
        _sealed_host_path(path, is_dir=False)
    if (PINNED_WORKER.is_relative_to(PINNED_UPSTREAM)
            or PINNED_PYTHON.is_relative_to(PINNED_CORE)):
        raise BrokerDenied("Broker and guest worker installation roots are confused")


class BrokerOwnedVMExecutor:
    """Single-VM lifecycle held entirely inside the broker's Windows process.

    No start() arguments are accepted from the agent. The class deliberately
    exposes no reset, step or evaluate operations without per-action MCP and
    Windows Hello authorization. Calling start() is reserved for a future,
    separate, owner-approved service entrypoint; never the audit IPC pipe.
    """

    def __init__(
        self,
        *,
        policy: BrokerServicePolicy,
        runtime_preflight: Callable[[], None] = verify_sealed_vm_runtime,
        service_preflight: Callable[[], BrokerServicePolicy] = preflight_service,
        identity_source: Callable[[], str] = current_process_sid,
        factory: Callable[..., _VM] = OSWorldSubprocessVM,
    ) -> None:
        if type(policy) is not BrokerServicePolicy or policy.mode != "deny_only":
            raise BrokerDenied("Untrusted broker service configuration")
        self._policy = policy
        self._runtime_preflight = runtime_preflight
        self._service_preflight = service_preflight
        self._identity_source = identity_source
        self._factory = factory
        self._lock = threading.RLock()
        self._vm: _VM | None = None

    def _validate_identity(self) -> None:
        validate_service_identity(self._policy, actual_sid=self._identity_source())
        active_policy = self._service_preflight()
        if active_policy != self._policy:
            raise BrokerDenied("Service identity/policy changed after preflight")

    def start(self) -> BootIdentity:
        """Broker-local action only. No IPC route, arbitrary args or guest steps."""
        with self._lock:
            self._validate_identity()
            if self._vm is not None:
                raise BrokerDenied("Broker already owns an OSWorld VM")
            self._runtime_preflight()
            vm = self._factory(
                upstream=PINNED_UPSTREAM,
                worker=PINNED_WORKER,
                boot_timeout=900,
                assets=None,
                force_no_kvm=False,
                website_suffix=None,
            )
            boot = vm.boot
            if type(boot) is not BootIdentity:
                try:
                    vm.close()
                finally:
                    raise BrokerDenied("Broker worker returned no exact VM identity")
            self._vm = vm
            return boot

    def stop(self) -> None:
        """Best-effort cleanup of the broker-owned worker under the same token."""
        with self._lock:
            self._validate_identity()
            if self._vm is not None:
                vm, self._vm = self._vm, None
                vm.close()

    def __enter__(self) -> "BrokerOwnedVMExecutor":
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()
