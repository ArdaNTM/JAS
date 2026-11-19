"""Externally keyable read-only checkpoints for the existing Gateway audit ledger.

This module only attests to already-recorded *metadata*. It does not authorize
operations, persist the ledger, grant Owner approval, or provide WORM storage.
The HMAC key and checkpoints must be held outside the audit producer for an
independent verifier to detect replays, truncation and post-hoc re-chaining.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from typing import Sequence

from aura_core.enterprise.runtime_controls import AuditRecord, HashChainAuditLedger

_SCHEMA = "aura.audit.checkpoint.v1"
_GENESIS = "0" * 64
_MAX_RECORDS = 100_000
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class AuditCheckpoint:
    """No principal identifiers, arguments, transcripts or provider output."""

    schema: str
    sequence: int
    tail_hash: str
    scope_digest: str
    previous_mac: str
    mac: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "schema": self.schema,
            "sequence": self.sequence,
            "tail_hash": self.tail_hash,
            "scope_digest": self.scope_digest,
            "previous_mac": self.previous_mac,
            "mac": self.mac,
        }


def _key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ValueError("checkpoint key must contain at least 32 bytes")
    return value


def _scope(value: str) -> bytes:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError("scope must be a non-empty string of at most 256 characters")
    if value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("scope contains whitespace or control characters")
    return value.encode("utf-8")


def _canonical(fields: dict[str, object]) -> bytes:
    return json.dumps(fields, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _scope_digest(key: bytes, scope: bytes) -> str:
    return hmac.new(key, b"aura-audit-scope-v1\x00" + scope, hashlib.sha256).hexdigest()


def _mac(key: bytes, fields: dict[str, object]) -> str:
    return hmac.new(key, b"aura-audit-checkpoint-v1\x00" + _canonical(fields), hashlib.sha256).hexdigest()


def _fields(checkpoint: AuditCheckpoint) -> dict[str, object]:
    return {k: v for k, v in checkpoint.to_dict().items() if k != "mac"}


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and _HEX_64.fullmatch(value) is not None


def verify_audit_records(records: Sequence[AuditRecord]) -> bool:
    """Independently recompute the *existing* HashChainAuditLedger wire hash.

    Does not trust the mutable in-process ledger's own verify() result.
    """
    if not isinstance(records, (list, tuple)) or not 0 <= len(records) <= _MAX_RECORDS:
        return False
    previous = _GENESIS
    for expected_sequence, record in enumerate(records, 1):
        if not isinstance(record, AuditRecord):
            return False
        if type(record.sequence) is not int or record.sequence != expected_sequence:
            return False
        if not _is_digest(record.previous_hash) or not _is_digest(record.record_hash):
            return False
        if not hmac.compare_digest(record.previous_hash, previous):
            return False
        fields = {
            "sequence": record.sequence,
            "event_id": record.event_id,
            "timestamp": record.timestamp,
            "principal_id": record.principal_id,
            "action": record.action,
            "resource_scope": record.resource_scope,
            "outcome": record.outcome,
            "reason_code": record.reason_code,
            "previous_hash": record.previous_hash,
        }
        try:
            actual = hashlib.sha256(_canonical(fields)).hexdigest()
        except (TypeError, ValueError, OverflowError, UnicodeError):
            return False
        if not hmac.compare_digest(actual, record.record_hash):
            return False
        previous = record.record_hash
    return True


def _authentic(checkpoint: AuditCheckpoint, key: bytes, scope: bytes) -> bool:
    if not isinstance(checkpoint, AuditCheckpoint):
        return False
    if checkpoint.schema != _SCHEMA or type(checkpoint.sequence) is not int:
        return False
    if checkpoint.sequence < 0 or checkpoint.sequence > _MAX_RECORDS:
        return False
    if any(not _is_digest(value) for value in (
        checkpoint.tail_hash, checkpoint.scope_digest,
        checkpoint.previous_mac, checkpoint.mac,
    )):
        return False
    if not hmac.compare_digest(checkpoint.scope_digest, _scope_digest(key, scope)):
        return False
    return hmac.compare_digest(checkpoint.mac, _mac(key, _fields(checkpoint)))


def create_audit_checkpoint(
    ledger: HashChainAuditLedger,
    *,
    key: bytes,
    scope: str,
    previous: AuditCheckpoint | None = None,
) -> AuditCheckpoint:
    """Create an authenticated checkpoint from a *valid, immutable snapshot*.

    Previous checkpoints must be supplied by the verifier's independent store;
    they are not fetched from an untrusted ledger or inferred from timestamps.
    """
    secret, scope_bytes = _key(key), _scope(scope)
    if not isinstance(ledger, HashChainAuditLedger):
        raise TypeError("ledger must be the existing HashChainAuditLedger")
    snapshot = ledger.snapshot()
    if not verify_audit_records(snapshot):
        raise ValueError("audit chain is invalid or exceeds its record limit")
    if previous is not None:
        if not _authentic(previous, secret, scope_bytes):
            raise ValueError("previous checkpoint signature or scope is invalid")
        if previous.sequence > len(snapshot):
            raise ValueError("audit chain was truncated")
        preceding_tail = snapshot[previous.sequence - 1].record_hash if previous.sequence else _GENESIS
        if not hmac.compare_digest(previous.tail_hash, preceding_tail):
            raise ValueError("audit chain was rewritten after the previous checkpoint")
    fields: dict[str, object] = {
        "schema": _SCHEMA,
        "sequence": len(snapshot),
        "tail_hash": snapshot[-1].record_hash if snapshot else _GENESIS,
        "scope_digest": _scope_digest(secret, scope_bytes),
        "previous_mac": previous.mac if previous is not None else _GENESIS,
    }
    return AuditCheckpoint(**fields, mac=_mac(secret, fields))


def verify_audit_checkpoint(
    ledger: HashChainAuditLedger,
    checkpoint: AuditCheckpoint,
    *,
    key: bytes,
    scope: str,
    previous: AuditCheckpoint | None = None,
) -> bool:
    """Fail-closed, exact-head verification; append-only changes require a new checkpoint."""
    secret, scope_bytes = _key(key), _scope(scope)
    if not isinstance(ledger, HashChainAuditLedger):
        return False
    snapshot = ledger.snapshot()
    if not verify_audit_records(snapshot) or not _authentic(checkpoint, secret, scope_bytes):
        return False
    if checkpoint.sequence != len(snapshot):
        return False
    tail = snapshot[-1].record_hash if snapshot else _GENESIS
    if not hmac.compare_digest(checkpoint.tail_hash, tail):
        return False
    if previous is not None:
        if not _authentic(previous, secret, scope_bytes):
            return False
        if previous.sequence > checkpoint.sequence:
            return False
        preceding_tail = snapshot[previous.sequence - 1].record_hash if previous.sequence else _GENESIS
        if not hmac.compare_digest(previous.tail_hash, preceding_tail):
            return False
        if not hmac.compare_digest(checkpoint.previous_mac, previous.mac):
            return False
    return True
