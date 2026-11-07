"""Stage F2.2: authenticated Windows named-pipe broker client.

Only the independent AuraAuditor process should call this. The server's
Windows process token SID is verified BEFORE sending a request and again
AFTER receiving the reply. Returned data is never trusted on its own:
a separately pinned broker Ed25519 key must sign the exact, fresh nonce
and VM/run identifiers before an auditor may use the measurement.

This module does not issue host isolation receipts or invoke Docker.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
import secrets
import time
from collections.abc import Callable
from typing import Protocol

from .audit_broker_protocol import (
    BrokerDenied, OPERATION, PROTOCOL, parse_request,
)
from .audit_broker_receipt import verify_measurement
from .audit_broker_windows import (
    PIPE_NAME, MAX_RESPONSE_BYTES, current_process_sid,
)
from .audit_broker_service import SID_PATTERN

PIPE_CONNECT_TIMEOUT_MS = 5000
PIPE_IO_TIMEOUT_MS = 5000
_SECURITY_SQOS_PRESENT = 0x00100000
_SECURITY_IDENTIFICATION = 0x00010000
_FILE_FLAG_OVERLAPPED = 0x40000000
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_ERROR_IO_PENDING = 997


class BrokerPipeTransport(Protocol):
    def exchange(self, message: bytes, *, expected_service_sid: str) -> bytes:
        """Return a bounded reply from the OS-authenticated service."""


def _server_process_sid(pipe_handle: object) -> str:
    """Query Windows kernel pipe-server PID then that process token's User SID.

    Do not use the pipe name, a response header, or a caller-supplied PID as
    proof of who owns the other end of a named pipe.
    """
    if os.name != "nt":
        raise BrokerDenied("Broker pipe identity requires Windows")
    try:
        import win32api
        import win32con
        import win32security

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        func = kernel32.GetNamedPipeServerProcessId
        func.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
        func.restype = wintypes.BOOL
        pid = wintypes.ULONG()
        if not func(wintypes.HANDLE(int(pipe_handle)), ctypes.byref(pid)) or not pid.value:
            raise BrokerDenied("Cannot determine named-pipe server process")
        proc = win32api.OpenProcess(
            _PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
        )
        try:
            token = win32security.OpenProcessToken(proc, win32con.TOKEN_QUERY)
            try:
                user_sid = win32security.GetTokenInformation(
                    token, win32security.TokenUser
                )[0]
                return win32security.ConvertSidToStringSid(user_sid)
            finally:
                token.Close()
        finally:
            proc.Close()
    except BrokerDenied:
        raise
    except (OSError, ValueError, AttributeError, RuntimeError) as exc:
        raise BrokerDenied("Cannot authenticate broker process token") from exc


def _overlapped_transfer(handle, *, message: bytes | None, timeout_ms: int) -> bytes | int:
    """Bound both pipe I/O operations; cancellation/close on wait failure."""
    import pywintypes
    import win32event
    import win32file

    operation = pywintypes.OVERLAPPED()
    operation.hEvent = win32event.CreateEvent(None, True, False, None)
    try:
        if message is None:
            code, output = win32file.ReadFile(handle, MAX_RESPONSE_BYTES + 1, operation)
        else:
            code, output = win32file.WriteFile(handle, message, operation)
        if code == _ERROR_IO_PENDING:
            if win32event.WaitForSingleObject(operation.hEvent, timeout_ms) != win32event.WAIT_OBJECT_0:
                try:
                    win32file.CancelIoEx(handle, operation)
                except (OSError, AttributeError):
                    pass
                raise BrokerDenied("Timed out waiting for broker pipe")
            transferred = win32file.GetOverlappedResult(handle, operation, False)
        elif code == 0:
            # PyWin32 returns a full-size overlapped read buffer, even when
            # fewer bytes were received. Never trust len(output) as the count.
            transferred = (
                win32file.GetOverlappedResult(handle, operation, False)
                if message is None else output
            )
        else:
            raise BrokerDenied("Named-pipe I/O failed")
        if type(transferred) is not int or transferred < 0:
            raise BrokerDenied("Invalid named-pipe transfer size")
        if message is not None:
            if transferred != len(message):
                raise BrokerDenied("Truncated audit request transmission")
            return transferred
        if transferred > MAX_RESPONSE_BYTES:
            raise BrokerDenied("Broker reply is too large or malformed")
        try:
            return bytes(output[:transferred])
        except (TypeError, ValueError) as exc:
            raise BrokerDenied("Malformed Windows pipe response buffer") from exc
    finally:
        # Closing the event cannot make an unsafe response trusted.
        operation.hEvent.Close()


class WindowsBrokerPipe:
    """Native, bounded Windows transport; always enforces broker OS SID."""

    def exchange(self, message: bytes, *, expected_service_sid: str) -> bytes:
        if os.name != "nt":
            raise BrokerDenied("Windows named-pipe transport is unavailable")
        if (type(message) is not bytes
                or type(expected_service_sid) is not str
                or SID_PATTERN.fullmatch(expected_service_sid) is None):
            raise BrokerDenied("Malformed pipe message or broker identity")
        import win32con
        import win32file
        import win32pipe
        try:
            win32pipe.WaitNamedPipe(PIPE_NAME, PIPE_CONNECT_TIMEOUT_MS)
            handle = win32file.CreateFile(
                PIPE_NAME,
                win32con.GENERIC_READ | win32con.GENERIC_WRITE,
                0, None, win32con.OPEN_EXISTING,
                _FILE_FLAG_OVERLAPPED
                | _SECURITY_SQOS_PRESENT | _SECURITY_IDENTIFICATION,
                None,
            )
        except OSError as exc:
            raise BrokerDenied("Trusted broker pipe is not available") from exc
        try:
            if _server_process_sid(handle) != expected_service_sid:
                raise BrokerDenied("Broker is owned by an unexpected Windows SID")
            win32pipe.SetNamedPipeHandleState(
                handle, win32pipe.PIPE_READMODE_MESSAGE, None, None
            )
            _overlapped_transfer(handle, message=message, timeout_ms=PIPE_IO_TIMEOUT_MS)
            raw = _overlapped_transfer(handle, message=None, timeout_ms=PIPE_IO_TIMEOUT_MS)
            if _server_process_sid(handle) != expected_service_sid:
                raise BrokerDenied("Broker process changed during request")
            return raw
        except BrokerDenied:
            raise
        except (OSError, ValueError, AttributeError, RuntimeError) as exc:
            raise BrokerDenied("Trusted broker pipe exchange failed") from exc
        finally:
            handle.Close()


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise BrokerDenied("Duplicate broker response key")
        result[key] = value
    return result


def request_signed_measurement(
    *,
    run_id: str,
    container_id: str,
    expected_auditor_sid: str,
    expected_service_sid: str,
    pinned_broker_public_key: bytes,
    transport: BrokerPipeTransport | None = None,
) -> dict[str, object]:
    """Fail-closed client; a mock transport is only for offline regression tests.

    Real caller must pin a trusted broker key independently of the AURA agent.
    A valid measurement is NOT an OSWorld isolation receipt or Owner approval.
    """
    if (type(expected_auditor_sid) is not str
            or type(expected_service_sid) is not str
            or SID_PATTERN.fullmatch(expected_auditor_sid) is None
            or SID_PATTERN.fullmatch(expected_service_sid) is None
            or expected_auditor_sid == expected_service_sid):
        raise BrokerDenied("Invalid or shared auditor and broker identities")
    if current_process_sid() != expected_auditor_sid:
        raise BrokerDenied("IPC requests require the pinned AuraAuditor account")
    now = int(time.time())
    fields = {
        "protocol": PROTOCOL,
        "operation": OPERATION,
        "run_id": run_id,
        "container_id": container_id,
        "nonce": secrets.token_hex(16),
        "issued_at": now,
    }
    wire = json.dumps(fields, separators=(",", ":"), sort_keys=True).encode("ascii")
    request = parse_request(wire, now=now)
    pipe = WindowsBrokerPipe() if transport is None else transport
    raw = pipe.exchange(wire, expected_service_sid=expected_service_sid)
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_RESPONSE_BYTES:
        raise BrokerDenied("Missing or oversized broker reply")
    try:
        envelope = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrokerDenied("Unparseable broker measurement") from exc
    # In particular, a deny-only JSON response can never become evidence.
    return verify_measurement(
        envelope, pinned_public_key=pinned_broker_public_key,
        expected_nonce=request.nonce,
        expected_container_id=request.container_id,
        expected_run_id=request.run_id,
        now=int(time.time()),
    )
