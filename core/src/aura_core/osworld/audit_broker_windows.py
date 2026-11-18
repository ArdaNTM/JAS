"""Windows-only one-request named-pipe transport for a trusted audit broker.

Not a service installer and not a Docker permission grant. The caller provides
a trusted handler; the peer SID is derived from the Windows thread token after
ReadFile + ImpersonateNamedPipeClient, NEVER from request JSON.
Runtime startup requires a separate service SID from the agent and auditor.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable

from .audit_broker_protocol import (
    BrokerDenied, MAX_REQUEST_BYTES, parse_request,
)

PIPE_NAME = r"\\.\pipe\aura-osworld-audit-v1"
FIRST_PIPE_INSTANCE = 0x00080000
PIPE_REJECT_REMOTE_CLIENTS = 0x00000008
MAX_RESPONSE_BYTES = 4096


def _win32():
    if os.name != "nt":
        raise BrokerDenied("Windows named-pipe transport is unavailable")
    try:
        import pywintypes
        import win32api
        import win32con
        import win32file
        import win32pipe
        import win32security
    except ImportError as exc:
        raise BrokerDenied("Pinned Windows IPC dependencies unavailable") from exc
    return pywintypes, win32api, win32con, win32file, win32pipe, win32security


def current_process_sid() -> str:
    _, win32api, win32con, _, _, security = _win32()
    token = security.OpenProcessToken(
        win32api.GetCurrentProcess(), win32con.TOKEN_QUERY
    )
    return security.ConvertSidToStringSid(
        security.GetTokenInformation(token, security.TokenUser)[0]
    )


def authenticated_pipe_peer_sid(handle: object) -> str:
    """Read the OS impersonation token; always revert, including on errors.

    Only call AFTER reading a complete message from the named-pipe client.
    """
    _, win32api, win32con, _, pipe, security = _win32()
    impersonated = False
    try:
        pipe.ImpersonateNamedPipeClient(handle)
        impersonated = True
        token = security.OpenThreadToken(
            win32api.GetCurrentThread(), win32con.TOKEN_QUERY, True
        )
        return security.ConvertSidToStringSid(
            security.GetTokenInformation(token, security.TokenUser)[0]
        )
    finally:
        if impersonated:
            security.RevertToSelf()


def _pipe_security_attributes(auditor_sid: str, service_sid: str):
    pywintypes, _, _, _, _, security = _win32()
    # Windows SID syntax is checked by ConvertStringSidToSid; never accept
    # an SDDL fragment from an untrusted caller.
    security.ConvertStringSidToSid(auditor_sid)
    security.ConvertStringSidToSid(service_sid)
    sddl = (
        "D:P"
        "(A;;GA;;;SY)"
        "(A;;GA;;;BA)"
        f"(A;;GA;;;{service_sid})"
        f"(A;;GRGW;;;{auditor_sid})"
    )
    descriptor = security.ConvertStringSecurityDescriptorToSecurityDescriptor(
        sddl, security.SDDL_REVISION_1
    )
    attributes = pywintypes.SECURITY_ATTRIBUTES()
    attributes.SECURITY_DESCRIPTOR = descriptor
    attributes.bInheritHandle = False
    return attributes


def serve_once(
    *,
    auditor_sid: str,
    expected_service_sid: str,
    forbidden_agent_sid: str,
    handler: Callable[[bytes, str], bytes],
) -> None:
    """Single message; fail closed and never return exception details.

    The handler MUST validate requests and produce a signed measurement.
    No Docker operation is implemented or authorized by this transport alone.
    """
    if not callable(handler):
        raise BrokerDenied("Missing trusted request handler")
    service_sid = current_process_sid()
    if (not expected_service_sid or not forbidden_agent_sid
            or service_sid != expected_service_sid
            or service_sid in (auditor_sid, forbidden_agent_sid)
            or auditor_sid == forbidden_agent_sid):
        raise BrokerDenied("Broker must run under isolated service identity")

    _, _, _, win32file, win32pipe, _ = _win32()
    attrs = _pipe_security_attributes(auditor_sid, service_sid)

    handle = win32pipe.CreateNamedPipe(
        PIPE_NAME,
        win32pipe.PIPE_ACCESS_DUPLEX | FIRST_PIPE_INSTANCE,
        win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE
        | win32pipe.PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
        1, MAX_RESPONSE_BYTES, MAX_REQUEST_BYTES + 1, 1000, attrs,
    )

    try:
        try:
            win32pipe.ConnectNamedPipe(handle, None)
        except Exception as exc:
            # ERROR_PIPE_CONNECTED means a client connected before Connect.
            if getattr(exc, "winerror", None) != 535:
                raise

        try:
            _, raw = win32file.ReadFile(handle, MAX_REQUEST_BYTES + 1)
            if type(raw) not in (bytes, bytearray):
                raise BrokerDenied("Malformed pipe read")
            peer_sid = authenticated_pipe_peer_sid(handle)
            if peer_sid != auditor_sid:
                raise BrokerDenied("Unauthorized named-pipe client")
            # Validate syntax before calling any privileged application code.
            import time
            parse_request(bytes(raw), now=int(time.time()))
            response = handler(bytes(raw), peer_sid)
            if type(response) is not bytes or not 1 <= len(response) <= MAX_RESPONSE_BYTES:
                raise BrokerDenied("Invalid broker measurement response")
        except Exception:
            response = b'{"status":"ISOLATION_BLOCKED","signed":false}'
        win32file.WriteFile(handle, response)
    finally:
        win32file.CloseHandle(handle)
