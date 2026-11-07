"""F2.5 Windows Docker daemon *access boundary* inspection.

The Docker Desktop Linux engine named pipe is a privileged host interface.
Access to the pipe is sufficient to defeat any claim that the caller is an
unprivileged AURA agent. A failed connection is only a denial if Windows
returns ERROR_ACCESS_DENIED; a missing/busy engine is *not* isolation proof.

This module makes no Docker API calls, installs no services, changes no ACLs
or group memberships, and never grants authority based on agent-provided
observations. An administrator must compare observations gathered locally
under each *real* Windows token; no assertion from this module can by itself
activate an audit service or produce a signed isolation receipt.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Callable, Literal

from .audit_broker_protocol import BrokerDenied
from .audit_broker_service import BrokerServicePolicy, SID_PATTERN

# Matches the separately pinned desktop-linux Docker CLI context.
DOCKER_DESKTOP_LINUX_PIPE = r"\\.\pipe\dockerDesktopLinuxEngine"
ACCESS_DENIED = 5
PIPE_BUSY = 231
PIPE_MISSING = 2
_ACCESS = frozenset({"allowed", "denied", "unavailable"})
_ROLE = frozenset({"agent", "auditor", "broker"})


@dataclass(frozen=True, slots=True)
class DaemonPipeObservation:
    role: str
    principal_sid: str
    endpoint: str
    access: Literal["allowed", "denied", "unavailable"]
    windows_error: int | None


def _validate_observation(item: DaemonPipeObservation) -> None:
    if (type(item) is not DaemonPipeObservation
            or type(item.role) is not str or item.role not in _ROLE
            or type(item.principal_sid) is not str
            or SID_PATTERN.fullmatch(item.principal_sid) is None
            or item.endpoint != DOCKER_DESKTOP_LINUX_PIPE
            or type(item.access) is not str or item.access not in _ACCESS):
        raise BrokerDenied("Untrusted Docker daemon access observation")
    if (item.access == "allowed" and item.windows_error is not None
            or item.access == "denied" and item.windows_error != ACCESS_DENIED
            or item.access == "unavailable" and
                (type(item.windows_error) is not int
                 or item.windows_error in (0, ACCESS_DENIED))):
        raise BrokerDenied("Inconsistent Windows daemon access result")


def _native_pipe_access() -> tuple[str, int | None]:
    """Attempt *only an open/close* of the pinned Docker Engine pipe.

    Never send Docker commands, even informational Docker commands, to test
    access. A successful CreateFile means the account has a dangerous
    capability, not that Docker is safe or isolated.
    """
    if os.name != "nt":
        raise BrokerDenied("Docker daemon token access inspection requires Windows")
    try:
        import win32con
        import win32file
        handle = win32file.CreateFile(
            DOCKER_DESKTOP_LINUX_PIPE,
            win32con.GENERIC_READ | win32con.GENERIC_WRITE,
            0, None, win32con.OPEN_EXISTING, 0, None,
        )
        try:
            return "allowed", None
        finally:
            handle.Close()
    except OSError as exc:
        winerror = getattr(exc, "winerror", None)
        if type(winerror) is not int:
            raise BrokerDenied("Windows daemon pipe access result is indeterminate") from exc
        if winerror == ACCESS_DENIED:
            return "denied", ACCESS_DENIED
        # Missing/busy/broken endpoint is not a proof of access denial.
        return "unavailable", winerror


def inspect_current_principal(
    *, role: str, expected_sid: str,
    sid_source: Callable[[], str] | None = None,
    access_probe: Callable[[], tuple[str, int | None]] | None = None,
) -> DaemonPipeObservation:
    """Require actual OS identity; no self-reported 'agent' success claim."""
    if (type(role) is not str or role not in _ROLE
            or type(expected_sid) is not str
            or SID_PATTERN.fullmatch(expected_sid) is None):
        raise BrokerDenied("Unexpected daemon boundary principal")
    if sid_source is None:
        from .audit_broker_windows import current_process_sid
        sid_source = current_process_sid
    if access_probe is None:
        access_probe = _native_pipe_access
    if sid_source() != expected_sid:
        raise BrokerDenied("Windows token does not match pinned principal")
    access, error = access_probe()
    observed = DaemonPipeObservation(
        role, expected_sid, DOCKER_DESKTOP_LINUX_PIPE, access, error,
    )
    _validate_observation(observed)
    return observed


def validate_boundary_observations(
    observations: tuple[DaemonPipeObservation, ...],
    *,
    policy: BrokerServicePolicy,
) -> None:
    """Evaluate *only* independent operator evidence, never authorize a service.

    Need positive proof same pinned daemon is available to broker and
    explicit Windows ACCESS_DENIED for agent *and* auditor. A missing
    endpoint, simple group lookup or timeout never passes this test.
    """
    if type(policy) is not BrokerServicePolicy or type(observations) is not tuple:
        raise BrokerDenied("Invalid boundary evidence")
    expected = {
        "agent": policy.agent_sid,
        "auditor": policy.auditor_sid,
        "broker": policy.service_sid,
    }
    if (len(set(expected.values())) != 3 or len(observations) != 3
            or {o.role for o in observations if type(o) is DaemonPipeObservation}
               != set(expected)):
        raise BrokerDenied("Boundary requires exactly three independent principals")
    result = {}
    for obs in observations:
        _validate_observation(obs)
        if obs.principal_sid != expected[obs.role]:
            raise BrokerDenied("Daemon probe token mismatched broker policy")
        result[obs.role] = obs.access
    if result != {"agent": "denied", "auditor": "denied", "broker": "allowed"}:
        raise BrokerDenied("Agent/auditor still have daemon access or Docker is unavailable")


def require_no_agent_daemon_access(
    *, agent_sid: str,
    sid_source: Callable[[], str] | None = None,
    access_probe: Callable[[], tuple[str, int | None]] | None = None,
) -> None:
    """Sole live-runner gate; true only for real ERROR_ACCESS_DENIED.

    This is not sufficient to run OSWorld: its worker currently requires
    Docker. Stage F2.5 therefore refuses live start until a broker-owned
    VM worker transport replaces the direct Docker subprocess.
    """
    obs = inspect_current_principal(
        role="agent", expected_sid=agent_sid,
        sid_source=sid_source, access_probe=access_probe,
    )
    if obs.access != "denied":
        raise BrokerDenied("AURA agent must not be authorized to the Docker Engine pipe")
