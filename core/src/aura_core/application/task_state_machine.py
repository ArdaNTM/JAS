"""Persistent, deterministic task state machine for governed orchestration.

This module records task lifecycle and dependency state only. It does not execute
tools, grant capabilities, or make authorization decisions; execution remains
behind the existing task runtime, MCP Gateway, and Permission Engine.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from aura_core.kernel.events import EventBus, KernelEvent


class TaskState(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    BLOCKED = "blocked"


TERMINAL_STATES = {
    TaskState.SUCCEEDED,
    TaskState.FAILED,
    TaskState.CANCELLED,
    TaskState.TIMED_OUT,
    TaskState.BLOCKED,
}
_ALLOWED_TRANSITIONS = {
    TaskState.PENDING: {TaskState.READY, TaskState.CANCELLED, TaskState.TIMED_OUT, TaskState.BLOCKED},
    TaskState.READY: {TaskState.RUNNING, TaskState.CANCELLED, TaskState.TIMED_OUT, TaskState.BLOCKED},
    TaskState.RUNNING: {TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED, TaskState.TIMED_OUT},
    TaskState.SUCCEEDED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
    TaskState.TIMED_OUT: set(),
    TaskState.BLOCKED: set(),
}


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(frozen=True, slots=True)
class TaskStateRecord:
    task_id: str
    principal_id: str
    goal: str
    state: TaskState
    dependencies: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    deadline: datetime | None = None
    cancellation_requested: bool = False
    result_summary: str | None = None
    error: str | None = None
    revision: int = 0


class TaskStateMachine:
    """SQLite-backed state/dependency ledger with transactional transitions."""

    def __init__(self, database_path: str | Path, event_bus: EventBus | None = None) -> None:
        self.database_path = str(database_path)
        self.event_bus = event_bus
        if self.database_path != ":memory:":
            Path(self.database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self.database_path, timeout=5.0, check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        if self.database_path != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS orchestration_tasks (
                task_id TEXT PRIMARY KEY,
                principal_id TEXT NOT NULL,
                goal TEXT NOT NULL,
                state TEXT NOT NULL,
                dependencies_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deadline TEXT,
                cancellation_requested INTEGER NOT NULL DEFAULT 0,
                result_summary TEXT,
                error TEXT,
                revision INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_orchestration_tasks_owner_state "
            "ON orchestration_tasks(principal_id, state)"
        )
        self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def create_task(
        self,
        *,
        principal_id: str,
        goal: str,
        task_id: str | None = None,
        dependencies: tuple[str, ...] | list[str] = (),
        timeout_seconds: float | None = None,
    ) -> TaskStateRecord:
        if not principal_id.strip():
            raise ValueError("principal_id is required")
        if not goal.strip():
            raise ValueError("goal is required")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        new_id = task_id or str(uuid4())
        deps = tuple(dict.fromkeys(dependencies))
        if new_id in deps:
            raise ValueError("task cannot depend on itself")
        now = _now()
        deadline = now + timedelta(seconds=timeout_seconds) if timeout_seconds is not None else None

        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                if self._connection.execute(
                    "SELECT 1 FROM orchestration_tasks WHERE task_id = ?", (new_id,)
                ).fetchone():
                    raise ValueError(f"Task already exists: {new_id}")
                for dependency_id in deps:
                    dependency = self._connection.execute(
                        "SELECT principal_id, state FROM orchestration_tasks WHERE task_id = ?",
                        (dependency_id,),
                    ).fetchone()
                    if dependency is None:
                        raise ValueError(f"Unknown dependency: {dependency_id}")
                    if dependency["principal_id"] != principal_id:
                        raise ValueError("dependencies must belong to the same principal")
                initial = TaskState.READY if all(
                    self._state_for(dependency_id) == TaskState.SUCCEEDED for dependency_id in deps
                ) else TaskState.PENDING
                self._connection.execute(
                    """INSERT INTO orchestration_tasks
                    (task_id, principal_id, goal, state, dependencies_json, created_at,
                     updated_at, deadline, revision)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                    (new_id, principal_id, goal[:4000], initial.value,
                     json.dumps(deps), now.isoformat(), now.isoformat(),
                     deadline.isoformat() if deadline else None),
                )
                self._connection.commit()
            except BaseException:
                self._connection.rollback()
                raise
        record = self.get(new_id, principal_id=principal_id)
        self._emit("TaskCreated", record)
        if record.state == TaskState.READY:
            self._emit("TaskReady", record)
        return record

    def get(self, task_id: str, *, principal_id: str) -> TaskStateRecord:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM orchestration_tasks WHERE task_id = ? AND principal_id = ?",
                (task_id, principal_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown task: {task_id}")
        return self._record(row)

    def list_tasks(self, *, principal_id: str) -> tuple[TaskStateRecord, ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM orchestration_tasks WHERE principal_id = ? ORDER BY created_at, task_id",
                (principal_id,),
            ).fetchall()
        return tuple(self._record(row) for row in rows)

    def transition(
        self,
        task_id: str,
        *,
        principal_id: str,
        target: TaskState,
        result_summary: str | None = None,
        error: str | None = None,
    ) -> TaskStateRecord:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT * FROM orchestration_tasks WHERE task_id = ? AND principal_id = ?",
                    (task_id, principal_id),
                ).fetchone()
                if row is None:
                    raise KeyError(f"Unknown task: {task_id}")
                current = TaskState(row["state"])
                if target not in _ALLOWED_TRANSITIONS[current]:
                    raise ValueError(f"Invalid task transition: {current.value} -> {target.value}")
                if target == TaskState.READY and not self._dependencies_succeeded(row):
                    raise ValueError("task dependencies are not all succeeded")
                now = _now()
                self._connection.execute(
                    """UPDATE orchestration_tasks
                    SET state = ?, updated_at = ?, result_summary = ?, error = ?, revision = revision + 1
                    WHERE task_id = ? AND principal_id = ?""",
                    (target.value, now.isoformat(),
                     (result_summary[:4000] if result_summary else None),
                     (error[:2000] if error else None), task_id, principal_id),
                )
                self._connection.commit()
            except BaseException:
                self._connection.rollback()
                raise
        record = self.get(task_id, principal_id=principal_id)
        self._emit("TaskStateChanged", record, extra={"previous_state": current.value})
        if target == TaskState.SUCCEEDED:
            self._refresh_dependents(record)
        if target in {TaskState.FAILED, TaskState.CANCELLED, TaskState.TIMED_OUT, TaskState.BLOCKED}:
            self._block_dependents(record)
        return record

    def request_cancel(self, task_id: str, *, principal_id: str) -> TaskStateRecord:
        record = self.get(task_id, principal_id=principal_id)
        if record.state in TERMINAL_STATES:
            return record
        if record.state == TaskState.RUNNING:
            with self._lock:
                self._connection.execute(
                    """UPDATE orchestration_tasks SET cancellation_requested = 1,
                    updated_at = ?, revision = revision + 1
                    WHERE task_id = ? AND principal_id = ?""",
                    (_now().isoformat(), task_id, principal_id),
                )
                self._connection.commit()
            updated = self.get(task_id, principal_id=principal_id)
            self._emit("TaskCancellationRequested", updated)
            return updated
        return self.transition(
            task_id, principal_id=principal_id, target=TaskState.CANCELLED
        )

    def expire_timeouts(self, *, now: datetime | None = None) -> tuple[TaskStateRecord, ...]:
        current_time = now or _now()
        with self._lock:
            rows = self._connection.execute(
                """SELECT task_id, principal_id FROM orchestration_tasks
                WHERE deadline IS NOT NULL AND deadline <= ?
                AND state IN (?, ?, ?)""",
                (current_time.isoformat(), TaskState.PENDING.value,
                 TaskState.READY.value, TaskState.RUNNING.value),
            ).fetchall()
        expired: list[TaskStateRecord] = []
        for row in rows:
            try:
                expired.append(self.transition(
                    row["task_id"], principal_id=row["principal_id"],
                    target=TaskState.TIMED_OUT, error="Task deadline exceeded",
                ))
            except ValueError:
                # Another worker may have completed the task after the query.
                continue
        return tuple(expired)

    def _state_for(self, task_id: str) -> TaskState:
        row = self._connection.execute(
            "SELECT state FROM orchestration_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        return TaskState(row["state"])

    def _dependencies_succeeded(self, row: sqlite3.Row) -> bool:
        deps = json.loads(row["dependencies_json"])
        return all(self._state_for(dependency_id) == TaskState.SUCCEEDED for dependency_id in deps)

    def _refresh_dependents(self, completed: TaskStateRecord) -> None:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM orchestration_tasks WHERE principal_id = ? AND state = ?",
                (completed.principal_id, TaskState.PENDING.value),
            ).fetchall()
        for row in rows:
            if completed.task_id not in json.loads(row["dependencies_json"]):
                continue
            if all(
                self.get(dependency_id, principal_id=completed.principal_id).state == TaskState.SUCCEEDED
                for dependency_id in json.loads(row["dependencies_json"])
            ):
                self.transition(
                    row["task_id"], principal_id=completed.principal_id,
                    target=TaskState.READY,
                )

    def _block_dependents(self, failed: TaskStateRecord) -> None:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM orchestration_tasks WHERE principal_id = ? AND state IN (?, ?)",
                (failed.principal_id, TaskState.PENDING.value, TaskState.READY.value),
            ).fetchall()
        for row in rows:
            if failed.task_id in json.loads(row["dependencies_json"]):
                self.transition(
                    row["task_id"], principal_id=failed.principal_id,
                    target=TaskState.BLOCKED,
                    error=f"Dependency {failed.task_id} ended as {failed.state.value}",
                )

    def _record(self, row: sqlite3.Row) -> TaskStateRecord:
        return TaskStateRecord(
            task_id=row["task_id"], principal_id=row["principal_id"],
            goal=row["goal"], state=TaskState(row["state"]),
            dependencies=tuple(json.loads(row["dependencies_json"])),
            created_at=_parse_time(row["created_at"]) or _now(),
            updated_at=_parse_time(row["updated_at"]) or _now(),
            deadline=_parse_time(row["deadline"]),
            cancellation_requested=bool(row["cancellation_requested"]),
            result_summary=row["result_summary"], error=row["error"],
            revision=int(row["revision"]),
        )

    def _emit(
        self, event_type: str, record: TaskStateRecord,
        *, extra: dict[str, Any] | None = None,
    ) -> None:
        if self.event_bus is None:
            return
        payload = {
            "task_id": record.task_id,
            "principal_id": record.principal_id,
            "state": record.state.value,
            "dependencies": list(record.dependencies),
            "revision": record.revision,
            "cancellation_requested": record.cancellation_requested,
        }
        if extra:
            payload.update(extra)
        self.event_bus.publish(KernelEvent(
            event_type=event_type,
            source_component="aura.task_state_machine",
            payload=payload,
            correlation_id=record.task_id,
        ))
