"""Async PostgreSQL implementation of the workflow lifecycle store.

This adapter preserves idempotent creation and optimistic concurrency. It is
not selected by application composition yet; remote mode must remain fail-closed
until all durable stores and checkpoint artifacts are migrated and verified.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from aura_core.enterprise.workflow_store import (
    InvalidWorkflowTransition,
    WorkflowConflict,
    WorkflowRecord,
    WorkflowStatus,
    _ALLOWED_TRANSITIONS,
    _required,
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class PostgreSQLWorkflowStore:
    """Remote workflow state with transaction-scoped row locks and CAS versions."""

    def __init__(self, database_url: str, *, engine: AsyncEngine | None = None) -> None:
        if not isinstance(database_url, str) or not database_url.strip():
            raise ValueError("AURA_DATABASE_URL is required for PostgreSQLWorkflowStore")
        if not database_url.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise ValueError("AURA_DATABASE_URL must use PostgreSQL")
        self._engine = engine or create_async_engine(database_url, pool_pre_ping=True)
        self._owns_engine = engine is None

    async def initialize(self) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(text("""
                CREATE TABLE IF NOT EXISTS aura_workflows (
                    workflow_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    principal_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN
                        ('pending','running','succeeded','failed','cancelled')),
                    version BIGINT NOT NULL CHECK (version >= 1),
                    checkpoint_ref TEXT,
                    failure_code TEXT,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                )
            """))

    @staticmethod
    def _record(row) -> WorkflowRecord | None:
        if row is None:
            return None
        return WorkflowRecord(
            workflow_id=row["workflow_id"],
            idempotency_key=row["idempotency_key"],
            principal_id=row["principal_id"],
            task_id=row["task_id"],
            status=WorkflowStatus(row["status"]),
            version=int(row["version"]),
            checkpoint_ref=row["checkpoint_ref"],
            failure_code=row["failure_code"],
            created_at=row["created_at"].isoformat(),
            updated_at=row["updated_at"].isoformat(),
        )

    async def create(
        self, *, workflow_id: str, idempotency_key: str,
        principal_id: str, task_id: str,
    ) -> WorkflowRecord:
        workflow_id = _required(workflow_id, "workflow_id")
        idempotency_key = _required(idempotency_key, "idempotency_key")
        principal_id = _required(principal_id, "principal_id")
        task_id = _required(task_id, "task_id")
        now = datetime.now(timezone.utc)
        async with self._engine.begin() as connection:
            inserted = await connection.execute(text("""
                INSERT INTO aura_workflows (
                    workflow_id, idempotency_key, principal_id, task_id, status,
                    version, checkpoint_ref, failure_code, created_at, updated_at
                ) VALUES (
                    :workflow_id, :idempotency_key, :principal_id, :task_id,
                    'pending', 1, NULL, NULL, :now, :now
                )
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING *
            """), {
                "workflow_id": workflow_id, "idempotency_key": idempotency_key,
                "principal_id": principal_id, "task_id": task_id, "now": now,
            })
            row = inserted.mappings().one_or_none()
            if row is None:
                existing = await connection.execute(text("""
                    SELECT * FROM aura_workflows
                    WHERE idempotency_key = :key FOR UPDATE
                """), {"key": idempotency_key})
                row = existing.mappings().one_or_none()
                record = self._record(row)
                if record is None:
                    raise WorkflowConflict("Workflow idempotency conflict; retry creation")
                if record.principal_id != principal_id or record.task_id != task_id:
                    raise WorkflowConflict("Idempotency key is already bound to another workflow identity")
                return record
            return self._record(row)

    async def get(self, workflow_id: str) -> WorkflowRecord | None:
        workflow_id = _required(workflow_id, "workflow_id")
        async with self._engine.connect() as connection:
            result = await connection.execute(text("""
                SELECT * FROM aura_workflows WHERE workflow_id = :workflow_id
            """), {"workflow_id": workflow_id})
            return self._record(result.mappings().one_or_none())

    async def get_by_idempotency_key(self, idempotency_key: str) -> WorkflowRecord | None:
        idempotency_key = _required(idempotency_key, "idempotency_key")
        async with self._engine.connect() as connection:
            result = await connection.execute(text("""
                SELECT * FROM aura_workflows WHERE idempotency_key = :key
            """), {"key": idempotency_key})
            return self._record(result.mappings().one_or_none())

    async def transition(
        self, workflow_id: str, *, expected_version: int,
        target: WorkflowStatus, failure_code: str | None = None,
    ) -> WorkflowRecord:
        workflow_id = _required(workflow_id, "workflow_id")
        if type(expected_version) is not int or expected_version < 1:
            raise ValueError("expected_version must be a positive integer")
        if not isinstance(target, WorkflowStatus):
            raise ValueError("target must be a WorkflowStatus")
        if failure_code is not None:
            failure_code = _required(failure_code, "failure_code", max_length=128)
        if target is WorkflowStatus.FAILED and failure_code is None:
            failure_code = "unspecified_failure"
        if target is not WorkflowStatus.FAILED and failure_code is not None:
            raise ValueError("failure_code is only valid for FAILED transitions")
        async with self._engine.begin() as connection:
            result = await connection.execute(text("""
                SELECT * FROM aura_workflows WHERE workflow_id = :id FOR UPDATE
            """), {"id": workflow_id})
            record = self._record(result.mappings().one_or_none())
            if record is None:
                raise KeyError("Workflow not found")
            if record.version != expected_version:
                raise WorkflowConflict("Workflow version changed; reload before retrying")
            if target not in _ALLOWED_TRANSITIONS[record.status]:
                raise InvalidWorkflowTransition(
                    f"Transition {record.status.value} -> {target.value} is not allowed"
                )
            result = await connection.execute(text("""
                UPDATE aura_workflows
                SET status = :status, version = version + 1,
                    failure_code = :failure_code, updated_at = :now
                WHERE workflow_id = :id AND version = :version
                RETURNING *
            """), {
                "status": target.value, "failure_code": failure_code,
                "now": datetime.now(timezone.utc), "id": workflow_id,
                "version": expected_version,
            })
            updated = self._record(result.mappings().one_or_none())
            if updated is None:
                raise WorkflowConflict("Workflow changed during transition")
            return updated

    async def save_checkpoint(
        self, workflow_id: str, *, expected_version: int, checkpoint_ref: str,
    ) -> WorkflowRecord:
        workflow_id = _required(workflow_id, "workflow_id")
        checkpoint_ref = _required(checkpoint_ref, "checkpoint_ref", max_length=1024)
        if type(expected_version) is not int or expected_version < 1:
            raise ValueError("expected_version must be a positive integer")
        async with self._engine.begin() as connection:
            result = await connection.execute(text("""
                SELECT * FROM aura_workflows WHERE workflow_id = :id FOR UPDATE
            """), {"id": workflow_id})
            record = self._record(result.mappings().one_or_none())
            if record is None:
                raise KeyError("Workflow not found")
            if record.version != expected_version:
                raise WorkflowConflict("Workflow version changed; reload before retrying")
            if record.status is not WorkflowStatus.RUNNING:
                raise InvalidWorkflowTransition("Checkpoints may only be saved for RUNNING workflows")
            result = await connection.execute(text("""
                UPDATE aura_workflows
                SET checkpoint_ref = :checkpoint_ref, version = version + 1, updated_at = :now
                WHERE workflow_id = :id AND version = :version
                RETURNING *
            """), {
                "checkpoint_ref": checkpoint_ref, "now": datetime.now(timezone.utc),
                "id": workflow_id, "version": expected_version,
            })
            updated = self._record(result.mappings().one_or_none())
            if updated is None:
                raise WorkflowConflict("Workflow changed during checkpoint save")
            return updated

    async def close(self) -> None:
        if self._owns_engine:
            await self._engine.dispose()
