"""SQLite-backed, one-time governed approval records.

Only authorization identity and opaque digests are persisted. Raw tool arguments,
prompts, credentials, provider responses, and request payloads must never be stored
here. Callers should compute request_fingerprint with a keyed HMAC when the
canonical request could contain sensitive or low-entropy values.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Callable


_DIGEST_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_MAX_TTL_SECONDS = 30 * 24 * 60 * 60


class ApprovalConflict(RuntimeError):
    """Raised for identity mismatches, stale versions, or concurrent updates."""


class InvalidApprovalTransition(ValueError):
    """Raised when an approval cannot make the requested state transition."""


class ApprovalExpired(InvalidApprovalTransition):
    """Raised when an approval's deadline has passed."""


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CONSUMED = "consumed"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    approval_id: str
    principal_id: str
    capability_id: str
    operation_id: str
    resource_scope: str
    request_fingerprint: str
    policy_digest: str
    status: ApprovalStatus
    version: int
    requested_at: str
    expires_at: str
    approver_id: str | None
    decided_at: str | None
    consumed_at: str | None
    revoked_by: str | None
    revoked_at: str | None


def _required(value: str, name: str, *, max_length: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    value = value.strip()
    if len(value) > max_length or any(ord(ch) < 32 for ch in value):
        raise ValueError(f"{name} is invalid")
    return value


def _digest(value: str, name: str) -> str:
    value = _required(value, name, max_length=64)
    if not _DIGEST_RE.fullmatch(value):
        raise ValueError(f"{name} must be a 64-character hexadecimal SHA-256 digest")
    return value.lower()


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("clock must return a datetime")
    if value.tzinfo is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat(timespec="microseconds")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


class SQLiteApprovalStore:
    """Transactional approval lifecycle store with compare-and-swap versions.

    Use a persistent SQLite path for durability. The caller is responsible for
    authenticating approver identities and re-evaluating current policy at the
    eventual execution boundary; this store only binds the approval to the
    supplied request fingerprint and policy digest.
    """

    def __init__(
        self,
        database_path: str,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._path = _required(database_path, "database_path", max_length=4096)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self._path, timeout=5.0, isolation_level=None, check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.execute("PRAGMA busy_timeout = 5000")
            self._connection.execute("PRAGMA foreign_keys = ON")
            if self._path != ":memory:":
                self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("""
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    principal_id TEXT NOT NULL,
                    capability_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    resource_scope TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL,
                    policy_digest TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN
                        ('pending', 'approved', 'denied', 'expired', 'consumed', 'revoked')),
                    version INTEGER NOT NULL CHECK(version >= 1),
                    requested_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    approver_id TEXT,
                    decided_at TEXT,
                    consumed_at TEXT,
                    revoked_by TEXT,
                    revoked_at TEXT
                )
            """)
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_approvals_principal_status "
                "ON approvals(principal_id, status)"
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "SQLiteApprovalStore":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    @staticmethod
    def _record(row: sqlite3.Row | None) -> ApprovalRecord | None:
        if row is None:
            return None
        return ApprovalRecord(
            approval_id=row["approval_id"],
            principal_id=row["principal_id"],
            capability_id=row["capability_id"],
            operation_id=row["operation_id"],
            resource_scope=row["resource_scope"],
            request_fingerprint=row["request_fingerprint"],
            policy_digest=row["policy_digest"],
            status=ApprovalStatus(row["status"]),
            version=row["version"],
            requested_at=row["requested_at"],
            expires_at=row["expires_at"],
            approver_id=row["approver_id"],
            decided_at=row["decided_at"],
            consumed_at=row["consumed_at"],
            revoked_by=row["revoked_by"],
            revoked_at=row["revoked_at"],
        )

    def create(
        self,
        *,
        principal_id: str,
        capability_id: str,
        operation_id: str,
        resource_scope: str,
        request_fingerprint: str,
        policy_digest: str,
        ttl_seconds: int | float = 900,
        approval_id: str | None = None,
    ) -> ApprovalRecord:
        principal_id = _required(principal_id, "principal_id")
        capability_id = _required(capability_id, "capability_id")
        operation_id = _required(operation_id, "operation_id")
        resource_scope = _required(resource_scope, "resource_scope")
        request_fingerprint = _digest(request_fingerprint, "request_fingerprint")
        policy_digest = _digest(policy_digest, "policy_digest")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float)):
            raise ValueError("ttl_seconds must be a positive finite number")
        if not math.isfinite(ttl_seconds) or not 0 < ttl_seconds <= _MAX_TTL_SECONDS:
            raise ValueError("ttl_seconds must be greater than zero and at most 30 days")
        approval_id = _required(approval_id or str(uuid.uuid4()), "approval_id")
        now = _utc(self._clock())
        requested_at = _iso(now)
        expires_at = _iso(now + timedelta(seconds=ttl_seconds))

        with self._lock:
            try:
                self._connection.execute(
                    """INSERT INTO approvals (
                        approval_id, principal_id, capability_id, operation_id, resource_scope,
                        request_fingerprint, policy_digest, status, version, requested_at,
                        expires_at, approver_id, decided_at, consumed_at, revoked_by, revoked_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, NULL, NULL, NULL, NULL, NULL)""",
                    (
                        approval_id, principal_id, capability_id, operation_id, resource_scope,
                        request_fingerprint, policy_digest, ApprovalStatus.PENDING.value,
                        requested_at, expires_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ApprovalConflict("Approval ID already exists") from exc
            row = self._connection.execute(
                "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
            ).fetchone()
            return self._record(row)

    def get(self, approval_id: str) -> ApprovalRecord | None:
        approval_id = _required(approval_id, "approval_id")
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
            ).fetchone()
            return self._record(row)

    def decide(
        self,
        approval_id: str,
        *,
        expected_version: int,
        approver_id: str,
        decision: ApprovalStatus,
    ) -> ApprovalRecord:
        approval_id = _required(approval_id, "approval_id")
        approver_id = _required(approver_id, "approver_id")
        self._validate_version(expected_version)
        if decision not in (ApprovalStatus.APPROVED, ApprovalStatus.DENIED):
            raise ValueError("decision must be APPROVED or DENIED")
        now = _utc(self._clock())
        expired = False
        with self._lock:
            connection = self._connection
            connection.execute("BEGIN IMMEDIATE")
            try:
                record = self._get_in_transaction(approval_id)
                if record is None:
                    raise KeyError("Approval not found")
                self._check_version(record, expected_version)
                if record.status is not ApprovalStatus.PENDING:
                    raise InvalidApprovalTransition("Only PENDING approvals can be decided")
                if now >= _parse_timestamp(record.expires_at):
                    self._update_status(
                        approval_id, expected_version, ApprovalStatus.EXPIRED, now,
                    )
                    expired = True
                else:
                    connection.execute(
                        """UPDATE approvals SET status = ?, version = version + 1,
                           approver_id = ?, decided_at = ?
                           WHERE approval_id = ? AND version = ?""",
                        (decision.value, approver_id, _iso(now), approval_id, expected_version),
                    )
                result = self._get_in_transaction(approval_id)
                connection.execute("COMMIT")
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
        if expired:
            raise ApprovalExpired("Approval expired before a decision was recorded")
        return self._record(result)

    def consume(
        self,
        approval_id: str,
        *,
        expected_version: int,
        principal_id: str,
        capability_id: str,
        operation_id: str,
        resource_scope: str,
        request_fingerprint: str,
        policy_digest: str,
    ) -> ApprovalRecord:
        """Atomically consume a matching APPROVED record exactly once."""
        approval_id = _required(approval_id, "approval_id")
        self._validate_version(expected_version)
        supplied = (
            _required(principal_id, "principal_id"),
            _required(capability_id, "capability_id"),
            _required(operation_id, "operation_id"),
            _required(resource_scope, "resource_scope"),
            _digest(request_fingerprint, "request_fingerprint"),
            _digest(policy_digest, "policy_digest"),
        )
        now = _utc(self._clock())
        expired = False
        with self._lock:
            connection = self._connection
            connection.execute("BEGIN IMMEDIATE")
            try:
                record = self._get_in_transaction(approval_id)
                if record is None:
                    raise KeyError("Approval not found")
                self._check_version(record, expected_version)
                if record.status is not ApprovalStatus.APPROVED:
                    raise InvalidApprovalTransition("Only APPROVED approvals can be consumed")
                if now >= _parse_timestamp(record.expires_at):
                    self._update_status(
                        approval_id, expected_version, ApprovalStatus.EXPIRED, now,
                    )
                    expired = True
                else:
                    expected = (
                        record.principal_id, record.capability_id, record.operation_id,
                        record.resource_scope, record.request_fingerprint, record.policy_digest,
                    )
                    if not all(
                        hmac.compare_digest(actual, wanted)
                        for actual, wanted in zip(supplied, expected, strict=True)
                    ):
                        raise ApprovalConflict("Approval does not match the current request or policy")
                    updated = connection.execute(
                        """UPDATE approvals SET status = ?, version = version + 1, consumed_at = ?
                           WHERE approval_id = ? AND version = ? AND status = ?""",
                        (
                            ApprovalStatus.CONSUMED.value, _iso(now), approval_id,
                            expected_version, ApprovalStatus.APPROVED.value,
                        ),
                    )
                    if updated.rowcount != 1:
                        raise ApprovalConflict("Approval changed during consumption")
                result = self._get_in_transaction(approval_id)
                connection.execute("COMMIT")
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
        if expired:
            raise ApprovalExpired("Approval expired before consumption")
        return self._record(result)

    def revoke(
        self,
        approval_id: str,
        *,
        expected_version: int,
        revoked_by: str,
    ) -> ApprovalRecord:
        approval_id = _required(approval_id, "approval_id")
        revoked_by = _required(revoked_by, "revoked_by")
        self._validate_version(expected_version)
        now = _utc(self._clock())
        with self._lock:
            connection = self._connection
            connection.execute("BEGIN IMMEDIATE")
            try:
                record = self._get_in_transaction(approval_id)
                if record is None:
                    raise KeyError("Approval not found")
                self._check_version(record, expected_version)
                if record.status is not ApprovalStatus.APPROVED:
                    raise InvalidApprovalTransition("Only APPROVED approvals can be revoked")
                if now >= _parse_timestamp(record.expires_at):
                    self._update_status(
                        approval_id, expected_version, ApprovalStatus.EXPIRED, now,
                    )
                    result = self._get_in_transaction(approval_id)
                    connection.execute("COMMIT")
                    raise_expired = True
                else:
                    connection.execute(
                        """UPDATE approvals SET status = ?, version = version + 1,
                           revoked_by = ?, revoked_at = ?
                           WHERE approval_id = ? AND version = ?""",
                        (
                            ApprovalStatus.REVOKED.value, revoked_by, _iso(now),
                            approval_id, expected_version,
                        ),
                    )
                    result = self._get_in_transaction(approval_id)
                    connection.execute("COMMIT")
                    raise_expired = False
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
        if raise_expired:
            raise ApprovalExpired("Approval expired before revocation")
        return self._record(result)

    @staticmethod
    def _validate_version(expected_version: int) -> None:
        if type(expected_version) is not int or expected_version < 1:
            raise ValueError("expected_version must be a positive integer")

    @staticmethod
    def _check_version(record: ApprovalRecord, expected_version: int) -> None:
        if record.version != expected_version:
            raise ApprovalConflict("Approval version changed; reload before retrying")

    def _get_in_transaction(self, approval_id: str) -> ApprovalRecord | None:
        row = self._connection.execute(
            "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
        ).fetchone()
        return self._record(row)

    def _update_status(
        self,
        approval_id: str,
        expected_version: int,
        target: ApprovalStatus,
        now: datetime,
    ) -> None:
        updated = self._connection.execute(
            """UPDATE approvals SET status = ?, version = version + 1
               WHERE approval_id = ? AND version = ?""",
            (target.value, approval_id, expected_version),
        )
        if updated.rowcount != 1:
            raise ApprovalConflict("Approval changed during state transition")
