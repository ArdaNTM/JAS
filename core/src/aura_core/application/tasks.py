"""HTTP-facing task coordination over the boundary-enforced agent runtime."""
from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, replace
from typing import Protocol

from aura_core.agent.runtime import ExecutionResult, Plan, PlanState, Task, _request_id_context
from aura_core.application.task_memory import TaskMemoryCoordinator
from aura_core.application.task_state_machine import TaskState, TaskStateMachine
from aura_core.enterprise.workflow_store import SQLiteWorkflowStore, WorkflowStatus


class TaskRuntime(Protocol):
    async def execute(self, task: Task, plan: Plan, cancelled=None) -> ExecutionResult:
        """Execute only through the existing authorized runtime."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class SubmittedTask:
    task: Task
    plan: Plan
    request_id: str | None = None
    dependencies: tuple[str, ...] = ()


class AgentTaskService:
    """Coordinates durable task state without bypassing Gateway authorization."""

    def __init__(
        self,
        runtime: TaskRuntime,
        *,
        memory: TaskMemoryCoordinator | None = None,
        state_machine: TaskStateMachine | None = None,
        workflow_store: SQLiteWorkflowStore | None = None,
    ) -> None:
        self._runtime = runtime
        self._memory = memory
        self._state_machine = state_machine
        self._workflow_store = workflow_store
        self._results: dict[str, ExecutionResult] = {}
        self._owners: dict[str, str] = {}
        self._task_locks: dict[str, asyncio.Lock] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}

    async def submit(self, submitted: SubmittedTask) -> ExecutionResult:
        """Submit one task; dependency-blocked tasks must be submitted via submit_chain."""
        self._validate_submission(submitted)
        if self._state_machine is not None:
            record = self._ensure_record(submitted)
            if record.state == TaskState.PENDING:
                raise RuntimeError("Task dependencies are not yet succeeded; use submit_chain()")
        return await self._execute_submitted(submitted)

    async def submit_chain(self, submissions: tuple[SubmittedTask, ...] | list[SubmittedTask]) -> tuple[ExecutionResult, ...]:
        """Persist a same-principal chain, then execute each task after dependencies succeed."""
        chain = tuple(submissions)
        if not chain:
            return ()
        principal_ids = {item.task.principal_id for item in chain}
        if len(principal_ids) != 1:
            raise ValueError("A task chain must use one principal")
        known_ids = {item.task.task_id for item in chain}
        if len(known_ids) != len(chain):
            raise ValueError("Task IDs in a chain must be unique")
        if self._state_machine is None:
            raise RuntimeError("submit_chain requires a persistent TaskStateMachine")
        # Only permit dependencies already persisted or included earlier in this chain.
        prepared: set[str] = set()
        for item in chain:
            self._validate_submission(item)
            unknown_later = set(item.dependencies) & (known_ids - prepared - {item.task.task_id})
            if unknown_later:
                raise ValueError("Task chain must be ordered before its dependents")
            self._ensure_record(item)
            prepared.add(item.task.task_id)
        results: list[ExecutionResult] = []
        for item in chain:
            record = self._state_machine.get(item.task.task_id, principal_id=item.task.principal_id)
            if record.state == TaskState.PENDING:
                raise RuntimeError(f"Task dependencies are not yet succeeded: {item.task.task_id}")
            results.append(await self._execute_submitted(item))
        return tuple(results)

    def cancel(self, task_id: str, *, principal_id: str) -> None:
        """Request cancellation only within the task owner's scope."""
        if self._state_machine is None:
            raise RuntimeError("Cancellation requires a persistent TaskStateMachine")
        self._state_machine.request_cancel(task_id, principal_id=principal_id)
        event = self._cancel_events.get(task_id)
        if event is not None:
            event.set()

    async def _execute_submitted(self, submitted: SubmittedTask) -> ExecutionResult:
        task_id = submitted.task.task_id
        lock = self._task_locks.setdefault(task_id, asyncio.Lock())
        async with lock:
            if task_id in self._results:
                raise ValueError(f"Task already submitted: {task_id}")
            task = submitted.task
            self._ensure_workflow(submitted)
            record = None
            if self._state_machine is not None:
                record = self._ensure_record(submitted)
                if record.state != TaskState.READY:
                    raise RuntimeError(f"Task is not ready for execution: {record.state.value}")
                record = self._state_machine.transition(
                    task_id, principal_id=task.principal_id, target=TaskState.RUNNING
                )
            try:
                self._transition_workflow(task_id, WorkflowStatus.RUNNING)
            except Exception:
                # Do not start runtime work unless both independent lifecycle
                # stores confirm the RUNNING transition. If workflow persistence
                # fails, fail the task before propagating the original error.
                # The workflow failure write is best-effort: if storage remains
                # unavailable, reconcile_workflow() can repair the pending
                # workflow from the terminal task record later.
                if self._state_machine is not None:
                    try:
                        current = self._state_machine.get(
                            task_id, principal_id=task.principal_id
                        )
                        if current.state is TaskState.RUNNING:
                            current = self._state_machine.transition(
                                task_id,
                                principal_id=task.principal_id,
                                target=TaskState.FAILED,
                                error="Workflow start persistence failed",
                            )
                        if current.state is TaskState.FAILED:
                            try:
                                self._transition_workflow(
                                    task_id,
                                    WorkflowStatus.FAILED,
                                    failure_code="workflow_start_persistence_failed",
                                )
                            except Exception:
                                # Preserve the original persistence failure;
                                # explicit reconciliation handles this gap.
                                pass
                    except Exception:
                        # Preserve the original persistence failure. A later
                        # reconciliation call surfaces any remaining mismatch.
                        pass
                raise
            cancel_event = asyncio.Event()
            self._cancel_events[task_id] = cancel_event
            memory_started = False
            if self._memory is not None:
                context = self._memory.begin(
                    principal_id=task.principal_id, task_id=task.task_id, goal=task.title
                )
                task = replace(task, memory_context=context)
                memory_started = True

            def cancelled() -> bool:
                if cancel_event.is_set():
                    return True
                if self._state_machine is None:
                    return False
                try:
                    current = self._state_machine.get(task_id, principal_id=task.principal_id)
                    if current.cancellation_requested:
                        cancel_event.set()
                        return True
                    return current.state in {TaskState.CANCELLED, TaskState.TIMED_OUT}
                except KeyError:
                    return True

            token = _request_id_context.set(submitted.request_id)
            try:
                execute_method = self._runtime.execute
                if "cancelled" in inspect.signature(execute_method).parameters:
                    execution = execute_method(task, submitted.plan, cancelled=cancelled)
                else:
                    execution = execute_method(task, submitted.plan)
                result = await asyncio.wait_for(execution, timeout=task.timeout_seconds)
            except asyncio.TimeoutError:
                if self._state_machine is not None:
                    self._state_machine.transition(
                        task_id, principal_id=task.principal_id, target=TaskState.TIMED_OUT,
                        error="Execution deadline exceeded",
                    )
                self._transition_workflow(task_id, WorkflowStatus.FAILED, failure_code="execution_timeout")
                raise
            except asyncio.CancelledError:
                target = TaskState.FAILED
                if self._state_machine is not None:
                    current = self._state_machine.get(task_id, principal_id=task.principal_id)
                    if current.state == TaskState.RUNNING:
                        target = TaskState.CANCELLED if current.cancellation_requested else TaskState.FAILED
                        self._state_machine.transition(task_id, principal_id=task.principal_id, target=target)
                if target is TaskState.CANCELLED:
                    self._transition_workflow(task_id, WorkflowStatus.CANCELLED)
                else:
                    self._transition_workflow(task_id, WorkflowStatus.FAILED, failure_code="execution_cancelled")
                raise
            except BaseException as exc:
                if self._state_machine is not None:
                    current = self._state_machine.get(task_id, principal_id=task.principal_id)
                    if current.state == TaskState.RUNNING:
                        self._state_machine.transition(
                            task_id, principal_id=task.principal_id, target=TaskState.FAILED,
                            error=f"Runtime raised {type(exc).__name__}",
                        )
                self._transition_workflow(task_id, WorkflowStatus.FAILED, failure_code=f"runtime_{type(exc).__name__}"[:128])
                if memory_started and self._memory is not None:
                    self._memory.finish(
                        principal_id=task.principal_id, task_id=task.task_id,
                        state="failed", summary="Task runtime raised an exception.",
                    )
                raise
            finally:
                _request_id_context.reset(token)
                self._cancel_events.pop(task_id, None)

            result_state = getattr(result.state, "value", str(result.state)).lower()
            target = (
                TaskState.CANCELLED if result.state is PlanState.CANCELLED
                else TaskState.SUCCEEDED if result.state is PlanState.SUCCEEDED
                else TaskState.FAILED
            )
            if self._state_machine is not None:
                current = self._state_machine.get(task_id, principal_id=task.principal_id)
                if current.state == TaskState.RUNNING:
                    if current.cancellation_requested or result.state is PlanState.CANCELLED:
                        target = TaskState.CANCELLED
                    elif result.state is PlanState.SUCCEEDED:
                        target = TaskState.SUCCEEDED
                    else:
                        target = TaskState.FAILED
                    summary = "; ".join(
                        f"{step.step_id}:{getattr(step.state, 'value', step.state)}"
                        for step in result.steps
                    )[:4000]
                    self._state_machine.transition(
                        task_id, principal_id=task.principal_id, target=target,
                        result_summary=summary,
                        error=summary if target == TaskState.FAILED else None,
                    )
            if target is TaskState.SUCCEEDED:
                self._transition_workflow(task_id, WorkflowStatus.SUCCEEDED)
            elif target is TaskState.CANCELLED:
                self._transition_workflow(task_id, WorkflowStatus.CANCELLED)
            else:
                self._transition_workflow(task_id, WorkflowStatus.FAILED, failure_code="task_execution_failed")
            if memory_started and self._memory is not None:
                memory_state = result_state if result_state in {"succeeded", "failed", "cancelled"} else "failed"
                summary = "; ".join(
                    f"{step.step_id}:{getattr(step.state, 'value', step.state)}"
                    for step in result.steps
                )[:4000]
                self._memory.finish(
                    principal_id=task.principal_id, task_id=task.task_id,
                    state=memory_state, summary=summary,
                )
            self._results[task_id] = result
            self._owners[task_id] = submitted.task.principal_id
            return result

    def _ensure_workflow(self, submitted: SubmittedTask) -> None:
        """Create the payload-minimizing workflow envelope before execution."""
        if self._workflow_store is None:
            return
        task = submitted.task
        self._workflow_store.create(
            workflow_id=task.task_id,
            idempotency_key=task.task_id,
            principal_id=task.principal_id,
            task_id=task.task_id,
        )

    def _transition_workflow(
        self,
        workflow_id: str,
        target: WorkflowStatus,
        *,
        failure_code: str | None = None,
    ) -> None:
        """Persist lifecycle changes using the store's optimistic version guard."""
        if self._workflow_store is None:
            return
        record = self._workflow_store.get(workflow_id)
        if record is None:
            raise RuntimeError(f"Workflow record missing for task: {workflow_id}")
        if record.status is target:
            return
        self._workflow_store.transition(
            workflow_id,
            expected_version=record.version,
            target=target,
            failure_code=failure_code,
        )

    def reconcile_workflow(self, task_id: str, *, principal_id: str):
        """Reconcile workflow metadata from the authoritative task-state ledger.

        This method never starts or resumes runtime execution. It only repairs
        lifecycle metadata after a partial persistence failure. Ambiguous
        contradictions are surfaced rather than silently overwriting terminal
        records.
        """
        if self._state_machine is None or self._workflow_store is None:
            raise RuntimeError("Workflow reconciliation requires both persistent stores")

        task = self._state_machine.get(task_id, principal_id=principal_id)
        workflow = self._workflow_store.get(task_id)
        if workflow is None:
            raise RuntimeError(f"Workflow record missing for task: {task_id}")
        if workflow.principal_id != principal_id or workflow.task_id != task_id:
            raise RuntimeError("Workflow identity does not match the requested task")

        target_by_task_state = {
            TaskState.PENDING: WorkflowStatus.PENDING,
            TaskState.READY: WorkflowStatus.PENDING,
            TaskState.RUNNING: WorkflowStatus.RUNNING,
            TaskState.SUCCEEDED: WorkflowStatus.SUCCEEDED,
            TaskState.FAILED: WorkflowStatus.FAILED,
            TaskState.TIMED_OUT: WorkflowStatus.FAILED,
            TaskState.BLOCKED: WorkflowStatus.FAILED,
            TaskState.CANCELLED: WorkflowStatus.CANCELLED,
        }
        target = target_by_task_state[task.state]
        if workflow.status is target:
            return workflow

        terminal = {
            WorkflowStatus.SUCCEEDED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }
        if workflow.status in terminal:
            raise RuntimeError(
                f"Cannot reconcile terminal workflow {workflow.status.value} "
                f"against task state {task.state.value}"
            )
        if target is WorkflowStatus.PENDING:
            raise RuntimeError(
                f"Cannot roll workflow back to pending from {workflow.status.value}"
            )

        # A task can finish between its RUNNING write and the workflow RUNNING
        # write. Preserve valid store transitions while repairing that gap.
        if workflow.status is WorkflowStatus.PENDING and target is WorkflowStatus.SUCCEEDED:
            workflow = self._workflow_store.transition(
                task_id, expected_version=workflow.version, target=WorkflowStatus.RUNNING
            )
        failure_code = None
        if target is WorkflowStatus.FAILED:
            failure_code = (
                "reconciled_task_timeout" if task.state is TaskState.TIMED_OUT
                else "reconciled_task_blocked" if task.state is TaskState.BLOCKED
                else "reconciled_task_failure"
            )
        return self._workflow_store.transition(
            task_id,
            expected_version=workflow.version,
            target=target,
            failure_code=failure_code,
        )

    def _ensure_record(self, submitted: SubmittedTask):
        if self._state_machine is None:
            return None
        task = submitted.task
        try:
            record = self._state_machine.get(task.task_id, principal_id=task.principal_id)
            if record.dependencies != tuple(submitted.dependencies):
                raise ValueError("Submitted dependencies do not match persisted task record")
            return record
        except KeyError:
            return self._state_machine.create_task(
                principal_id=task.principal_id,
                task_id=task.task_id,
                goal=task.title,
                dependencies=submitted.dependencies,
                timeout_seconds=task.timeout_seconds,
            )

    @staticmethod
    def _validate_submission(submitted: SubmittedTask) -> None:
        if submitted.plan is not None and submitted.plan.task_id != submitted.task.task_id:
            raise ValueError("Plan does not belong to submitted task")
        if len(set(submitted.dependencies)) != len(submitted.dependencies):
            raise ValueError("Task dependencies must be unique")

    def get_for_owner(self, task_id: str, principal_id: str) -> ExecutionResult:
        if self._owners.get(task_id) != principal_id:
            raise KeyError(f"Unknown task: {task_id}")
        return self.get(task_id)

    def get(self, task_id: str) -> ExecutionResult:
        try:
            return self._results[task_id]
        except KeyError as exc:
            raise KeyError(f"Unknown task: {task_id}") from exc
