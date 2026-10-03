from __future__ import annotations
import os
from fastapi import WebSocketException, status

def verify_ws_token(token: str | None) -> bool:
    expected = os.getenv("AURA_WS_SECRET", "aura-secure-token-123")
    if not token or token != expected:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
    return True
