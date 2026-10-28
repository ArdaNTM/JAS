"""Async PostgreSQL approval store preserving one-time authorization semantics.

This adapter is intentionally separate from the SQLite implementation until
production composition is migrated and the remote-mode integration suite passes.
"""
from __future__ import annotations

import hmac
import math
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from aura_core.enterprise.approval_store import (
    ApprovalConflict, ApprovalExpired, ApprovalRecord, ApprovalStatus,
    InvalidApprovalTransition, _MAX_TTL_SECONDS, _digest, _required,
    _parse_timestamp,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class PostgreSQLApprovalStore:
    """Remote, transactional approvals with principal binding and one-time consume."""

    def __init__(self, database_url: str, *, engine: AsyncEngine | None = None, clock=None) -> None:
        if not isinstance(database_url, str) or not database_url.strip():
            raise ValueError("AURA_DATABASE_URL is required for PostgreSQLApprovalStore")
        if not database_url.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise ValueError("AURA_DATABASE_URL must use PostgreSQL")
        self._engine = engine or create_async_engine(database_url, pool_pre_ping=True)
        self._owns_engine = engine is None
        self._clock = clock or _now

    async def initialize(self) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS aura_approvals (
                    approval_id TEXT PRIMARY KEY,
                    principal_id TEXT NOT NULL,
                    capability_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    resource_scope TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL,
                    policy_digest TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN
                      ('pending','approved','denied','expired','consumed','revoked')),
                    version BIGINT NOT NULL CHECK(version >= 1),
                    requested_at TIMESTAMPTZ NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL,
                    approver_id TEXT,
                    decided_at TIMESTAMPTZ,
                    consumed_at TIMESTAMPTZ,
                    revoked_by TEXT,
                    revoked_at TIMESTAMPTZ
                )
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_aura_approvals_principal_status
                ON aura_approvals(principal_id, status)
            """))

    @staticmethod
    def _record(row) -> ApprovalRecord | None:
        if row is None:
            return None
        def stamp(key):
            value = row[key]
            return value.astimezone(timezone.utc).isoformat() if value else None
        return ApprovalRecord(
            approval_id=row["approval_id"], principal_id=row["principal_id"],
            capability_id=row["capability_id"], operation_id=row["operation_id"],
            resource_scope=row["resource_scope"], request_fingerprint=row["request_fingerprint"],
            policy_digest=row["policy_digest"], status=ApprovalStatus(row["status"]),
            version=int(row["version"]), requested_at=stamp("requested_at"),
            expires_at=stamp("expires_at"), approver_id=row["approver_id"],
            decided_at=stamp("decided_at"), consumed_at=stamp("consumed_at"),
            revoked_by=row["revoked_by"], revoked_at=stamp("revoked_at"),
        )

    async def create(
        self, *, principal_id: str, capability_id: str, operation_id: str,
        resource_scope: str, request_fingerprint: str, policy_digest: str,
        ttl_seconds: int | float = 900, approval_id: str | None = None,
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
        now = self._clock()
        async with self._engine.begin() as conn:
            result = await conn.execute(text("""
                INSERT INTO aura_approvals (
                    approval_id, principal_id, capability_id, operation_id, resource_scope,
                    request_fingerprint, policy_digest, status, version, requested_at, expires_at,
                    approver_id, decided_at, consumed_at, revoked_by, revoked_at
                ) VALUES (:id,:principal,:capability,:operation,:scope,:fingerprint,:policy,
                          'pending',1,:now,:expires,NULL,NULL,NULL,NULL,NULL)
                ON CONFLICT (approval_id) DO NOTHING RETURNING *
            """), {"id":approval_id,"principal":principal_id,"capability":capability_id,
                   "operation":operation_id,"scope":resource_scope,"fingerprint":request_fingerprint,
                   "policy":policy_digest,"now":now,"expires":now+timedelta(seconds=ttl_seconds)})
            row = result.mappings().one_or_none()
            if row is None:
                raise ApprovalConflict("Approval ID already exists")
            return self._record(row)

    async def get(self, approval_id: str) -> ApprovalRecord | None:
        approval_id = _required(approval_id, "approval_id")
        async with self._engine.connect() as conn:
            result = await conn.execute(text("SELECT * FROM aura_approvals WHERE approval_id=:id"),
                                        {"id": approval_id})
            return self._record(result.mappings().one_or_none())

    async def decide(self, approval_id: str, *, expected_version: int,
                     approver_id: str, decision: ApprovalStatus) -> ApprovalRecord:
        approval_id = _required(approval_id, "approval_id")
        approver_id = _required(approver_id, "approver_id")
        self._check_version(expected_version)
        if decision not in (ApprovalStatus.APPROVED, ApprovalStatus.DENIED):
            raise ValueError("decision must be APPROVED or DENIED")
        now = self._clock()
        expired = False
        async with self._engine.begin() as conn:
            result = await conn.execute(text("SELECT * FROM aura_approvals WHERE approval_id=:id FOR UPDATE"),
                                        {"id": approval_id})
            record = self._record(result.mappings().one_or_none())
            if record is None:
                raise KeyError("Approval not found")
            self._check_current(record, expected_version)
            if record.status is not ApprovalStatus.PENDING:
                raise InvalidApprovalTransition("Only PENDING approvals can be decided")
            if now >= _parse_timestamp(record.expires_at):
                target, expired = ApprovalStatus.EXPIRED, True
            else:
                target = decision
            result = await conn.execute(text("""
                UPDATE aura_approvals SET status=:status, version=version+1,
                  approver_id=:approver, decided_at=:now
                WHERE approval_id=:id AND version=:version RETURNING *
            """), {"status":target.value,"approver":approver_id,"now":now,
                   "id":approval_id,"version":expected_version})
            updated = self._record(result.mappings().one())
        if expired:
            raise ApprovalExpired("Approval expired before a decision was recorded")
        return updated

    async def consume(self, approval_id: str, *, expected_version: int, principal_id: str,
                      capability_id: str, operation_id: str, resource_scope: str,
                      request_fingerprint: str, policy_digest: str) -> ApprovalRecord:
        approval_id = _required(approval_id, "approval_id")
        self._check_version(expected_version)
        supplied = (_required(principal_id,"principal_id"), _required(capability_id,"capability_id"),
                    _required(operation_id,"operation_id"), _required(resource_scope,"resource_scope"),
                    _digest(request_fingerprint,"request_fingerprint"), _digest(policy_digest,"policy_digest"))
        now = self._clock()
        expired = False
        async with self._engine.begin() as conn:
            result = await conn.execute(text("SELECT * FROM aura_approvals WHERE approval_id=:id FOR UPDATE"),
                                        {"id":approval_id})
            record = self._record(result.mappings().one_or_none())
            if record is None:
                raise KeyError("Approval not found")
            self._check_current(record, expected_version)
            if record.status is not ApprovalStatus.APPROVED:
                raise InvalidApprovalTransition("Only APPROVED approvals can be consumed")
            if now >= _parse_timestamp(record.expires_at):
                target, expired = ApprovalStatus.EXPIRED, True
            else:
                expected = (record.principal_id,record.capability_id,record.operation_id,
                            record.resource_scope,record.request_fingerprint,record.policy_digest)
                if supplied[:4] != expected[:4] or not (
                    hmac.compare_digest(supplied[4],expected[4]) and hmac.compare_digest(supplied[5],expected[5])
                ):
                    raise ApprovalConflict("Approval does not match the current request or policy")
                target = ApprovalStatus.CONSUMED
            result = await conn.execute(text("""
                UPDATE aura_approvals SET status=:status, version=version+1, consumed_at=:now
                WHERE approval_id=:id AND version=:version RETURNING *
            """), {"status":target.value,"now":now,"id":approval_id,"version":expected_version})
            updated = self._record(result.mappings().one())
        if expired:
            raise ApprovalExpired("Approval expired before consumption")
        return updated

    async def revoke(self, approval_id: str, *, expected_version: int, revoked_by: str) -> ApprovalRecord:
        approval_id = _required(approval_id, "approval_id")
        revoked_by = _required(revoked_by, "revoked_by")
        self._check_version(expected_version)
        now = self._clock()
        async with self._engine.begin() as conn:
            result = await conn.execute(text("SELECT * FROM aura_approvals WHERE approval_id=:id FOR UPDATE"),
                                        {"id":approval_id})
            record = self._record(result.mappings().one_or_none())
            if record is None:
                raise KeyError("Approval not found")
            self._check_current(record, expected_version)
            if record.status not in (ApprovalStatus.PENDING, ApprovalStatus.APPROVED):
                raise InvalidApprovalTransition("Only PENDING or APPROVED approvals can be revoked")
            result = await conn.execute(text("""
                UPDATE aura_approvals SET status='revoked', version=version+1,
                  revoked_by=:actor, revoked_at=:now
                WHERE approval_id=:id AND version=:version RETURNING *
            """), {"actor":revoked_by,"now":now,"id":approval_id,"version":expected_version})
            return self._record(result.mappings().one())

    @staticmethod
    def _check_version(version: int) -> None:
        if type(version) is not int or version < 1:
            raise ValueError("expected_version must be a positive integer")

    @staticmethod
    def _check_current(record: ApprovalRecord, version: int) -> None:
        if record.version != version:
            raise ApprovalConflict("Approval version changed; reload before retrying")

    async def close(self) -> None:
        if self._owns_engine:
            await self._engine.dispose()
