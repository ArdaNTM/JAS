"""F2.5 read-only Windows SCM service-logon identity attestation.

Windows service configuration is a privileged OS boundary: a valid-looking
service SID in JSON does NOT mean SCM runs under that identity. Require the
configured logon account to resolve to the *same* dedicated broker user SID,
and reject built-in service accounts. Never create/modify a Windows account,
service, password, local group or NTFS ACL.
"""
from __future__ import annotations

import os

from .audit_broker_protocol import BrokerDenied
from .audit_broker_service import (
    SERVICE_NAME, BrokerServicePolicy, SID_PATTERN,
    validate_service_identity,
)

_BUILTIN_LOGONS = frozenset({
    "localsystem", "nt authority\\system",
    "localservice", "nt authority\\localservice",
    "networkservice", "nt authority\\networkservice",
})


def validate_registered_logon(
    *, policy: BrokerServicePolicy, logon_name: str,
    resolved_sid: str,
) -> None:
    """Pure predicate for SCM-sourced account and Win32-resolved SID."""
    if (type(logon_name) is not str or not logon_name.strip()
            or logon_name.strip().lower() in _BUILTIN_LOGONS
            or type(resolved_sid) is not str
            or SID_PATTERN.fullmatch(resolved_sid) is None):
        raise BrokerDenied("Broker must use an independent local Windows user")
    if ("\n" in logon_name or "\r" in logon_name):
        raise BrokerDenied("Invalid configured SCM account")
    validate_service_identity(policy, actual_sid=resolved_sid)


def verify_registered_service_account(policy: BrokerServicePolicy) -> None:
    """Verify SCM registration without changing account/service state."""
    if os.name != "nt":
        raise BrokerDenied("Service registration attestation requires Windows")
    try:
        import win32con
        import win32security
        import win32service

        scm = win32service.OpenSCManager(
            None, None, win32con.SC_MANAGER_CONNECT,
        )
        try:
            handle = win32service.OpenService(
                scm, SERVICE_NAME, win32service.SERVICE_QUERY_CONFIG,
            )
            try:
                config = win32service.QueryServiceConfig(handle)
                if type(config) not in (tuple, list) or len(config) < 8:
                    raise BrokerDenied("Malformed Windows SCM service configuration")
                logon_name = config[7]
            finally:
                win32service.CloseServiceHandle(handle)
        finally:
            win32service.CloseServiceHandle(scm)
        resolved = win32security.ConvertSidToStringSid(
            win32security.LookupAccountName(None, logon_name)[0]
        )
        validate_registered_logon(
            policy=policy, logon_name=logon_name, resolved_sid=resolved,
        )
    except BrokerDenied:
        raise
    except (OSError, ValueError, IndexError, AttributeError) as exc:
        raise BrokerDenied("Cannot attest pinned Windows SCM service identity") from exc
