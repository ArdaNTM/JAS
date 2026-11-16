"""Fail-closed compatibility verifier for legacy WebSocket shared secrets.

New WebSocket endpoints must use WebSocketTicketManager's single-use, time-bound
tickets and authenticated ownership checks. This verifier is retained for older
integrations only; it does not grant PermissionEngine or MCP Gateway authority.
"""
from __future__ import annotations

import hmac
import os

from fastapi import WebSocketException, status


def _deny() -> None:
    # Do not expose configured secrets or caller-supplied credentials in errors.
    raise WebSocketException(
        code=status.WS_1008_POLICY_VIOLATION,
        reason="Unauthorized",
    )


def verify_ws_token(token: str | None) -> bool:
    """Accept only a valid explicit secret; missing/weak config always denies.

    AURA_WS_SECRET has no fallback and requires >=32 UTF-8 bytes. A deliberately
    bounded byte comparison avoids Unicode compare_digest exceptions and timing
    differences on token prefixes. No credential is logged or persisted.
    """
    expected = os.getenv("AURA_WS_SECRET")
    if not isinstance(expected, str):
        _deny()
    try:
        expected_bytes = expected.encode("utf-8")
    except UnicodeError:
        _deny()
    if len(expected_bytes) < 32:
        _deny()
    if expected != expected.strip() or any(ord(char) < 32 or ord(char) == 127 for char in expected):
        _deny()
    if not isinstance(token, str) or not token or len(token) > 4096:
        _deny()
    if token != token.strip() or any(ord(char) < 32 or ord(char) == 127 for char in token):
        _deny()
    try:
        supplied_bytes = token.encode("utf-8")
    except UnicodeError:
        _deny()
    if not hmac.compare_digest(supplied_bytes, expected_bytes):
        _deny()
    return True
