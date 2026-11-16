"""Legacy WebSocket verifier must never rely on insecure default credentials."""
import pytest
from fastapi import WebSocketException

from aura_core.security.auth import verify_ws_token

_STRONG = "legacy-ws-" + "s" * 40


def _denied(token):
    with pytest.raises(WebSocketException) as e:
        verify_ws_token(token)
    assert e.value.code == 1008
    assert e.value.reason == "Unauthorized"


def test_legacy_websocket_requires_explicit_secret(monkeypatch):
    monkeypatch.delenv("AURA_WS_SECRET", raising=False)
    _denied("aura-secure-token-123")
    _denied(None)
    _denied(_STRONG)


def test_rejects_old_default_password_even_when_provided_as_config(monkeypatch):
    monkeypatch.setenv("AURA_WS_SECRET", "aura-secure-token-123")
    _denied("aura-secure-token-123")


def test_strong_explicit_secret_is_accepted_exactly(monkeypatch):
    monkeypatch.setenv("AURA_WS_SECRET", _STRONG)
    assert verify_ws_token(_STRONG) is True


def test_wrong_prefix_wrong_suffix_and_empty_credentials_denied(monkeypatch):
    monkeypatch.setenv("AURA_WS_SECRET", _STRONG)
    for token in (None, "", _STRONG[:-1], _STRONG + "x", "x" + _STRONG,
                  _STRONG.replace("s", "t"), _STRONG + "\n", " " + _STRONG):
        _denied(token)


def test_config_rejects_newlines_control_chars_and_padding(monkeypatch):
    for secret in (_STRONG + "\r", "\t" + _STRONG, _STRONG + " ", "a" * 31,
                   "", "\ud800" + _STRONG):
        monkeypatch.setenv("AURA_WS_SECRET", secret)
        _denied(secret)


def test_rejects_nonstring_and_malformed_unicode_token(monkeypatch):
    monkeypatch.setenv("AURA_WS_SECRET", _STRONG)
    for token in (b"abc", 100, "a" * 4097, "\ud800" + _STRONG):
        _denied(token)


def test_unicode_secret_uses_byte_safe_constant_time_comparison(monkeypatch):
    secret = "ü" * 17
    monkeypatch.setenv("AURA_WS_SECRET", secret)
    assert verify_ws_token(secret) is True
    _denied(secret + "x")


def test_primary_one_time_websocket_ticket_manager_is_unchanged(monkeypatch):
    from aura_core.security.ws_ticket import WebSocketTicketManager
    monkeypatch.delenv("AURA_WS_SECRET", raising=False)
    manager = WebSocketTicketManager(secret="x" * 32, ttl_seconds=30)
    ticket = manager.issue()
    assert manager.verify(ticket.value) is True
    assert manager.verify(ticket.value) is False
