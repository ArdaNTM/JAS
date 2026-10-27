"""Transactional, payload-minimizing workflow state persistence.

This store persists workflow identity, lifecycle state, optimistic version, and an
opaque checkpoint reference. It deliberately does not serialize task arguments,
prompts, tool results, credentials, or provider payloads. The caller owns the
checkpoint artifact and must protect its storage separately.
"""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum


class WorkflowConflict(RuntimeError):
    """Raised when idempotency or optimistic concurrency checks conflict."""


class InvalidWorkflowTransition(ValueError):
    """Raised when a workflow lifecycle transition is not allowed."""


class WorkflowStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


_ALLOWED_TRANSITIONS = {
    WorkflowStatus.PENDING: {WorkflowStatus.RUNNING, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED},
    WorkflowStatus.RUNNING: {WorkflowStatus.SUCCEEDED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED},
    WorkflowStatus.SUCCEEDED: set(),
    WorkflowStatus.FAILED: set(),
    WorkflowStatus.CANCELLED: set(),
}


def _required(value: str, name: str, *, max_length: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    value = value.strip()
    if len(value) > max_length or any(ord(ch) < 32 for ch in value):
        raise ValueError(f"{name} is invalid")
    return value


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class WorkflowRecord:
    workflow_id: str
    idempotency_key: str
    principal_id: str
    task_id: str
    status: WorkflowStatus
    version: int
    checkpoint_ref: str | None
    failure_code: str | None
    created_at: str
    updated_at: str


class SQLiteWorkflowStore:
    """Transactional store with idempotent creation and compare-and-swap updates.

    Use a persistent database path for durability. An in-memory database is
    useful for tests but does not survive process termination.
    """

    def __init__(self, database_path: str) -> None:
        self._path = _required(database_path, "database_path", max_length=4096)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self._path, timeout=5.0, isolation_level=None, check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA busy_timeout = 5000")
            if self._path != ":memory:":
                self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    principal_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK(version >= 1),
                    checkpoint_ref TEXT,
                    failure_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "SQLiteWorkflowStore":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    @staticmethod
    def _record(row: sqlite3.Row | None) -> WorkflowRecord | None:
        if row is None:
            return None
        return WorkflowRecord(
            workflow_id=row["workflow_id"],
            idempotency_key=row["idempotency_key"],
            principal_id=row["principal_id"],
            task_id=row["task_id"],
            status=WorkflowStatus(row["status"]),
            version=row["version"],
            checkpoint_ref=row["checkpoint_ref"],
            failure_code=row["failure_code"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create(
        self, *, workflow_id: str, idempotency_key: str,
        principal_id: str, task_id: str,
    ) -> WorkflowRecord:
        workflow_id = _required(workflow_id, "workflow_id")
        idempotency_key = _required(idempotency_key, "idempotency_key")
        principal_id = _required(principal_id, "principal_id")
        task_id = _required(task_id, "task_id")
        now = _timestamp()
        with self._lock:
            connection = self._connection
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT * FROM workflows WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if existing is not None:
                    record = self._record(existing)
                    if record.principal_id != principal_id or record.task_id != task_id:
                        raise WorkflowConflict("Idempotency key is already bound to another workflow identity")
                    connection.execute("COMMIT")
                    return record
                connection.execute(
                    """INSERT INTO workflows (
                        workflow_id, idempotency_key, principal_id, task_id,
                        status, version, checkpoint_ref, failure_code, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 1, NULL, NULL, ?, ?)""",
                    (workflow_id, idempotency_key, principal_id, task_id,
                     WorkflowStatus.PENDING.value, now, now),
                )
                row = connection.execute(
                    "SELECT * FROM workflows WHERE workflow_id = ?", (workflow_id,)
                ).fetchone()
                connection.execute("COMMIT")
                return self._record(row)
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def get(self, workflow_id: str) -> WorkflowRecord | None:
        workflow_id = _required(workflow_id, "workflow_id")
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM workflows WHERE workflow_id = ?", (workflow_id,)
            ).fetchone()
            return self._record(row)

    def get_by_idempotency_key(self, idempotency_key: str) -> WorkflowRecord | None:
        idempotency_key = _required(idempotency_key, "idempotency_key")
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM workflows WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            return self._record(row)

    def transition(
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

        now = _timestamp()
        with self._lock:
            connection = self._connection
            connection.execute("BEGIN IMMEDIATE")
            try:
                current = connection.execute(
                    "SELECT * FROM workflows WHERE workflow_id = ?", (workflow_id,)
                ).fetchone()
                record = self._record(current)
                if record is None:
                    raise KeyError("Workflow not found")
                if record.version != expected_version:
                    raise WorkflowConflict("Workflow version changed; reload before retrying")
                if target not in _ALLOWED_TRANSITIONS[record.status]:
                    raise InvalidWorkflowTransition(
                        f"Transition {record.status.value} -> {target.value} is not allowed"
                    )
                updated = connection.execute(
                    """UPDATE workflows
                       SET status = ?, version = version + 1, failure_code = ?, updated_at = ?
                       WHERE workflow_id = ? AND version = ?""",
                    (target.value, failure_code, now, workflow_id, expected_version),
                )
                if updated.rowcount != 1:
                    raise WorkflowConflict("Workflow changed during transition")
                row = connection.execute(
                    "SELECT * FROM workflows WHERE workflow_id = ?", (workflow_id,)
                ).fetchone()
                connection.execute("COMMIT")
                return self._record(row)
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def save_checkpoint(
        self, workflow_id: str, *, expected_version: int, checkpoint_ref: str,
    ) -> WorkflowRecord:
        workflow_id = _required(workflow_id, "workflow_id")
        checkpoint_ref = _required(checkpoint_ref, "checkpoint_ref", max_length=1024)
        if type(expected_version) is not int or expected_version < 1:
            raise ValueError("expected_version must be a positive integer")
        now = _timestamp()
        with self._lock:
            connection = self._connection
            connection.execute("BEGIN IMMEDIATE")
            try:
                current = connection.execute(
                    "SELECT * FROM workflows WHERE workflow_id = ?", (workflow_id,)
                ).fetchone()
                record = self._record(current)
                if record is None:
                    raise KeyError("Workflow not found")
                if record.version != expected_version:
                    raise WorkflowConflict("Workflow version changed; reload before retrying")
                if record.status is not WorkflowStatus.RUNNING:
                    raise InvalidWorkflowTransition("Checkpoints may only be saved for RUNNING workflows")
                updated = connection.execute(
                    """UPDATE workflows SET checkpoint_ref = ?, version = version + 1, updated_at = ?
                       WHERE workflow_id = ? AND version = ?""",
                    (checkpoint_ref, now, workflow_id, expected_version),
                )
                if updated.rowcount != 1:
                    raise WorkflowConflict("Workflow changed during checkpoint save")
                row = connection.execute(
                    "SELECT * FROM workflows WHERE workflow_id = ?", (workflow_id,)
                ).fetchone()
                connection.execute("COMMIT")
                return self._record(row)
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
