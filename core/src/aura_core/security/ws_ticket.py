from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WebSocketTicket:
    value: str
    expires_at: int


class WebSocketTicketManager:
    """
    Short-lived, one-time WebSocket authentication tickets.

    Browser WebSocket clients cannot reliably set arbitrary Authorization
    headers. Therefore the UI first obtains a short-lived ticket over HTTPS
    and then presents that ticket during the WebSocket handshake.

    The long-lived AURA_EVENT_STREAM_TOKEN never reaches the browser.
    """

    def __init__(
        self,
        secret: str | None = None,
        ttl_seconds: int = 30,
    ) -> None:
        resolved = secret or os.getenv("AURA_EVENT_STREAM_TOKEN")

        if not resolved:
            raise RuntimeError(
                "AURA_EVENT_STREAM_TOKEN must be configured"
            )

        if len(resolved) < 32:
            raise RuntimeError(
                "AURA_EVENT_STREAM_TOKEN must contain at least 32 characters"
            )

        if ttl_seconds < 5 or ttl_seconds > 300:
            raise ValueError("ttl_seconds must be between 5 and 300")

        self._secret = resolved.encode("utf-8")
        self._ttl = ttl_seconds
        self._used: set[str] = set()

    def issue(self, subject: str = "aura-ui") -> WebSocketTicket:
        now = int(time.time())
        expires = now + self._ttl

        nonce = secrets.token_urlsafe(24)
        body = f"{subject}:{expires}:{nonce}"

        signature = hmac.new(
            self._secret,
            body.encode("utf-8"),
            hashlib.sha256,
        ).digest()

        encoded = base64.urlsafe_b64encode(
            signature
        ).decode("ascii").rstrip("=")

        return WebSocketTicket(
            value=f"{body}:{encoded}",
            expires_at=expires,
        )

    def verify(self, ticket: str, subject: str = "aura-ui") -> bool:
        if not ticket:
            return False

        if ticket in self._used:
            return False

        parts = ticket.split(":")

        if len(parts) != 4:
            return False

        ticket_subject, expires_text, nonce, supplied_signature = parts

        if ticket_subject != subject:
            return False

        try:
            expires = int(expires_text)
        except ValueError:
            return False

        if expires < int(time.time()):
            return False

        body = f"{ticket_subject}:{expires}:{nonce}"

        expected = hmac.new(
            self._secret,
            body.encode("utf-8"),
            hashlib.sha256,
        ).digest()

        expected_signature = base64.urlsafe_b64encode(
            expected
        ).decode("ascii").rstrip("=")

        if not hmac.compare_digest(
            supplied_signature,
            expected_signature,
        ):
            return False

        self._used.add(ticket)
        return True