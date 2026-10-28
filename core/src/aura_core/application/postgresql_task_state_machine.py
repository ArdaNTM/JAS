"""Async PostgreSQL-backed task state machine.

The API mirrors TaskStateMachine, but all I/O is awaitable. Tool execution and
authorization remain outside this module; this ledger only persists lifecycle
state and dependency gates.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from aura_core.application.task_state_machine import (
    TERMINAL_STATES, TaskState, TaskStateRecord, _ALLOWED_TRANSITIONS, _now,
)
from aura_core.kernel.events import EventBus, KernelEvent


class PostgreSQLTaskStateMachine:
    def __init__(self, database_url: str, event_bus: EventBus | None = None, *, engine: AsyncEngine | None = None) -> None:
        if not isinstance(database_url, str) or not database_url.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise ValueError("AURA_DATABASE_URL must use PostgreSQL")
        self.event_bus = event_bus
        self._engine = engine or create_async_engine(database_url, pool_pre_ping=True)
        self._owns_engine = engine is None

    async def initialize(self) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS aura_orchestration_tasks (
                    task_id TEXT PRIMARY KEY,
                    principal_id TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    state TEXT NOT NULL,
                    dependencies_json JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    deadline TIMESTAMPTZ,
                    cancellation_requested BOOLEAN NOT NULL DEFAULT FALSE,
                    result_summary TEXT,
                    error TEXT,
                    revision BIGINT NOT NULL DEFAULT 0
                )
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_aura_tasks_owner_state
                ON aura_orchestration_tasks(principal_id, state)
            """))

    @staticmethod
    def _record(row) -> TaskStateRecord:
        deps = row["dependencies_json"]
        if isinstance(deps, str):
            deps = json.loads(deps)
        return TaskStateRecord(
            task_id=row["task_id"], principal_id=row["principal_id"], goal=row["goal"],
            state=TaskState(row["state"]), dependencies=tuple(deps or ()),
            created_at=row["created_at"], updated_at=row["updated_at"],
            deadline=row["deadline"], cancellation_requested=bool(row["cancellation_requested"]),
            result_summary=row["result_summary"], error=row["error"], revision=int(row["revision"]),
        )

    async def create_task(self, *, principal_id: str, goal: str, task_id: str | None = None,
                          dependencies: tuple[str, ...] | list[str] = (),
                          timeout_seconds: float | None = None) -> TaskStateRecord:
        if not isinstance(principal_id, str) or not principal_id.strip():
            raise ValueError("principal_id is required")
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("goal is required")
        if timeout_seconds is not None and (isinstance(timeout_seconds, bool) or timeout_seconds <= 0):
            raise ValueError("timeout_seconds must be positive")
        new_id = task_id or str(uuid4())
        deps = tuple(dict.fromkeys(dependencies))
        if new_id in deps:
            raise ValueError("task cannot depend on itself")
        now = datetime.now(UTC)
        deadline = now + timedelta(seconds=timeout_seconds) if timeout_seconds is not None else None
        async with self._engine.begin() as conn:
            for dep_id in deps:
                result = await conn.execute(text("""
                    SELECT principal_id, state FROM aura_orchestration_tasks
                    WHERE task_id=:id FOR SHARE
                """), {"id": dep_id})
                dep = result.mappings().one_or_none()
                if dep is None:
                    raise ValueError(f"Unknown dependency: {dep_id}")
                if dep["principal_id"] != principal_id:
                    raise ValueError("dependencies must belong to the same principal")
            states = []
            for dep_id in deps:
                result = await conn.execute(text("SELECT state FROM aura_orchestration_tasks WHERE task_id=:id"), {"id": dep_id})
                states.append(TaskState(result.scalar_one()))
            initial = TaskState.READY if all(state is TaskState.SUCCEEDED for state in states) else TaskState.PENDING
            inserted = await conn.execute(text("""
                INSERT INTO aura_orchestration_tasks
                (task_id, principal_id, goal, state, dependencies_json, created_at, updated_at, deadline, revision)
                VALUES (:id,:principal,:goal,:state,CAST(:deps AS JSONB),:now,:now,:deadline,0)
                ON CONFLICT (task_id) DO NOTHING RETURNING *
            """), {"id": new_id, "principal": principal_id, "goal": goal[:4000],
                   "state": initial.value, "deps": json.dumps(deps), "now": now, "deadline": deadline})
            row = inserted.mappings().one_or_none()
            if row is None:
                raise ValueError(f"Task already exists: {new_id}")
            record = self._record(row)
        self._emit("TaskCreated", record)
        if record.state is TaskState.READY:
            self._emit("TaskReady", record)
        return record

    async def get(self, task_id: str, *, principal_id: str) -> TaskStateRecord:
        async with self._engine.connect() as conn:
            result = await conn.execute(text("""
                SELECT * FROM aura_orchestration_tasks WHERE task_id=:id AND principal_id=:principal
            """), {"id": task_id, "principal": principal_id})
            row = result.mappings().one_or_none()
        if row is None:
            raise KeyError(f"Unknown task: {task_id}")
        return self._record(row)

    async def list_tasks(self, *, principal_id: str) -> tuple[TaskStateRecord, ...]:
        async with self._engine.connect() as conn:
            result = await conn.execute(text("""
                SELECT * FROM aura_orchestration_tasks WHERE principal_id=:principal
                ORDER BY created_at, task_id
            """), {"principal": principal_id})
            rows = result.mappings().all()
        return tuple(self._record(row) for row in rows)

    async def transition(self, task_id: str, *, principal_id: str, target: TaskState,
                         result_summary: str | None = None, error: str | None = None) -> TaskStateRecord:
        async with self._engine.begin() as conn:
            result = await conn.execute(text("""
                SELECT * FROM aura_orchestration_tasks WHERE task_id=:id AND principal_id=:principal FOR UPDATE
            """), {"id": task_id, "principal": principal_id})
            row = result.mappings().one_or_none()
            if row is None:
                raise KeyError(f"Unknown task: {task_id}")
            current = TaskState(row["state"])
            if target not in _ALLOWED_TRANSITIONS[current]:
                raise ValueError(f"Invalid task transition: {current.value} -> {target.value}")
            deps = row["dependencies_json"]
            if isinstance(deps, str):
                deps = json.loads(deps)
            if target is TaskState.READY:
                for dep_id in deps:
                    dep_result = await conn.execute(text("""
                        SELECT state FROM aura_orchestration_tasks
                        WHERE task_id=:id AND principal_id=:principal
                    """), {"id": dep_id, "principal": principal_id})
                    dep_state = dep_result.scalar_one_or_none()
                    if dep_state != TaskState.SUCCEEDED.value:
                        raise ValueError("task dependencies are not all succeeded")
            now = datetime.now(UTC)
            result = await conn.execute(text("""
                UPDATE aura_orchestration_tasks SET state=:state, updated_at=:now,
                    result_summary=:summary, error=:error, revision=revision+1
                WHERE task_id=:id AND principal_id=:principal RETURNING *
            """), {"state": target.value, "now": now,
                   "summary": result_summary[:4000] if result_summary else None,
                   "error": error[:2000] if error else None, "id": task_id, "principal": principal_id})
            record = self._record(result.mappings().one())
        self._emit("TaskStateChanged", record, extra={"previous_state": current.value})
        if target is TaskState.SUCCEEDED:
            await self._refresh_dependents(record)
        if target in {TaskState.FAILED, TaskState.CANCELLED, TaskState.TIMED_OUT, TaskState.BLOCKED}:
            await self._block_dependents(record)
        return record

    async def request_cancel(self, task_id: str, *, principal_id: str) -> TaskStateRecord:
        record = await self.get(task_id, principal_id=principal_id)
        if record.state in TERMINAL_STATES:
            return record
        if record.state is TaskState.RUNNING:
            async with self._engine.begin() as conn:
                await conn.execute(text("""
                    UPDATE aura_orchestration_tasks SET cancellation_requested=TRUE,
                    updated_at=:now, revision=revision+1 WHERE task_id=:id AND principal_id=:principal
                """), {"now": datetime.now(UTC), "id": task_id, "principal": principal_id})
            updated = await self.get(task_id, principal_id=principal_id)
            self._emit("TaskCancellationRequested", updated)
            return updated
        return await self.transition(task_id, principal_id=principal_id, target=TaskState.CANCELLED)

    async def expire_timeouts(self, *, now: datetime | None = None) -> tuple[TaskStateRecord, ...]:
        async with self._engine.connect() as conn:
            result = await conn.execute(text("""
                SELECT task_id, principal_id FROM aura_orchestration_tasks
                WHERE deadline IS NOT NULL AND deadline <= :now
                AND state IN ('pending','ready','running')
            """), {"now": now or datetime.now(UTC)})
            rows = result.mappings().all()
        expired = []
        for row in rows:
            try:
                expired.append(await self.transition(row["task_id"], principal_id=row["principal_id"],
                    target=TaskState.TIMED_OUT, error="Task deadline exceeded"))
            except ValueError:
                continue
        return tuple(expired)

    async def _refresh_dependents(self, completed: TaskStateRecord) -> None:
        for record in await self.list_tasks(principal_id=completed.principal_id):
            if record.state is not TaskState.PENDING or completed.task_id not in record.dependencies:
                continue
            states = [await self.get(dep, principal_id=completed.principal_id) for dep in record.dependencies]
            if all(item.state is TaskState.SUCCEEDED for item in states):
                await self.transition(record.task_id, principal_id=record.principal_id, target=TaskState.READY)

    async def _block_dependents(self, failed: TaskStateRecord) -> None:
        for record in await self.list_tasks(principal_id=failed.principal_id):
            if record.state in {TaskState.PENDING, TaskState.READY} and failed.task_id in record.dependencies:
                await self.transition(record.task_id, principal_id=record.principal_id,
                    target=TaskState.BLOCKED, error=f"Dependency {failed.task_id} ended as {failed.state.value}")

    def _emit(self, event_type: str, record: TaskStateRecord, *, extra: dict | None = None) -> None:
        if self.event_bus is None:
            return
        payload = {"task_id": record.task_id, "principal_id": record.principal_id,
                   "state": record.state.value, "dependencies": list(record.dependencies),
                   "revision": record.revision, "cancellation_requested": record.cancellation_requested}
        if extra:
            payload.update(extra)
        self.event_bus.publish(KernelEvent(event_type=event_type, source_component="aura.task_state_machine",
            payload=payload, correlation_id=record.task_id))

    async def close(self) -> None:
        if self._owns_engine:
            await self._engine.dispose()
