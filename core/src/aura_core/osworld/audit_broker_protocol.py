"""Strict, side-effect-free OSWorld Docker audit request contract.

This module does NOT connect to Docker or authenticate Windows clients by itself.
The future named-pipe transport MUST supply peer_sid from the OS client token;
the future privileged backend MUST supply measured IDs from Docker inspection;
and claim_nonce MUST be backed by an atomic, durable uniqueness constraint.
Until those components exist, this module cannot authorize a live audit.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass


class BrokerDenied(PermissionError):
    """A broker request is invalid, unauthorized, stale, or replayed."""


PROTOCOL = "aura.docker-audit.request.v1"
OPERATION = "audit_osworld_network"
MAX_REQUEST_BYTES = 1024
MAX_AGE_SECONDS = 30
MAX_CLOCK_SKEW_SECONDS = 5
_FIELDS = frozenset({
    "protocol", "operation", "run_id", "container_id", "nonce", "issued_at",
})
_HEX32 = re.compile(r"[0-9a-f]{32}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_WINDOWS_SID = re.compile(r"S-1-5-21-(?:[0-9]+-){3}[0-9]+\Z")


@dataclass(frozen=True, slots=True)
class AuditRequest:
    run_id: str
    container_id: str
    nonce: str
    issued_at: int


def _deny_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    obj: dict[str, object] = {}
    for key, value in pairs:
        if key in obj:
            raise BrokerDenied("Duplicate JSON field")
        obj[key] = value
    return obj


def _deny_nonfinite(_: str) -> object:
    raise BrokerDenied("Non-finite JSON value")


def _validate_request(request: AuditRequest, *, now: int) -> None:
    if type(now) is not int:
        raise BrokerDenied("Invalid trusted clock")
    for value, pattern, name in (
        (request.run_id, _HEX32, "run_id"),
        (request.container_id, _HEX64, "container_id"),
        (request.nonce, _HEX32, "nonce"),
    ):
        if type(value) is not str or pattern.fullmatch(value) is None:
            raise BrokerDenied(f"Invalid {name}")
    if type(request.issued_at) is not int:
        raise BrokerDenied("Invalid issued_at")
    if not now - MAX_AGE_SECONDS <= request.issued_at <= now + MAX_CLOCK_SKEW_SECONDS:
        raise BrokerDenied("Stale or future request")


def parse_request(raw: bytes, *, now: int) -> AuditRequest:
    """Parse an exact-schema JSON message with no extra Docker operation inputs."""
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_REQUEST_BYTES:
        raise BrokerDenied("Invalid message size or encoding")
    try:
        obj = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_deny_duplicates,
            parse_constant=_deny_nonfinite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrokerDenied("Malformed JSON") from exc
    if type(obj) is not dict or set(obj) != _FIELDS:
        raise BrokerDenied("Unexpected request shape")
    if obj["protocol"] != PROTOCOL or type(obj["protocol"]) is not str:
        raise BrokerDenied("Protocol mismatch")
    if obj["operation"] != OPERATION or type(obj["operation"]) is not str:
        raise BrokerDenied("Operation is not permitted")
    req = AuditRequest(
        run_id=obj["run_id"],
        container_id=obj["container_id"],
        nonce=obj["nonce"],
        issued_at=obj["issued_at"],
    )
    _validate_request(req, now=now)
    return req


def authorize_request(
    request: AuditRequest,
    *,
    now: int,
    peer_sid: str,
    auditor_sid: str,
    measured_run_id: str,
    measured_container_id: str,
    claim_nonce: Callable[[str], bool],
) -> None:
    """Check identities and claim a one-time nonce before any privileged work.

    peer_sid: Windows named-pipe client's token SID, not caller JSON.
    measured_*: independently inspected Docker labels/IDs, not caller JSON.
    claim_nonce: atomic, persistent insert-if-absent (must return literal True).
    """
    if type(request) is not AuditRequest:
        raise BrokerDenied("Invalid request object")
    _validate_request(request, now=now)
    if (type(peer_sid) is not str or type(auditor_sid) is not str
            or _WINDOWS_SID.fullmatch(peer_sid) is None
            or _WINDOWS_SID.fullmatch(auditor_sid) is None
            or peer_sid != auditor_sid):
        raise BrokerDenied("Unauthorized Windows peer")
    if (type(measured_run_id) is not str or type(measured_container_id) is not str
            or _HEX32.fullmatch(measured_run_id) is None
            or _HEX64.fullmatch(measured_container_id) is None
            or request.run_id != measured_run_id
            or request.container_id != measured_container_id):
        raise BrokerDenied("VM ownership mismatch")
    if not callable(claim_nonce) or claim_nonce(request.nonce) is not True:
        raise BrokerDenied("Replay or invalid nonce store")
