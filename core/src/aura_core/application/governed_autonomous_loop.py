"""Bounded autonomous planning loop guarded by explicit policy and verification.

Planning and sandboxing are injected capabilities. The sandbox validates proposals
without executing tools; real execution is delegated to AgentTaskService, whose
runtime remains behind MCPGateway and Permission Engine.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Protocol, Sequence

from aura_core.application.tasks import AgentTaskService, SubmittedTask
from aura_core.kernel.events import EventBus, KernelEvent


@dataclass(frozen=True, slots=True)
class SandboxReport:
    accepted: bool
    summary: str
    findings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VerificationReport:
    passed: bool
    summary: str
    findings: tuple[str, ...] = ()


class AutonomousPlanner(Protocol):
    async def propose(
        self, *, goal: str, principal_id: str, resource_scope: str,
        iteration: int, feedback: tuple[str, ...],
    ) -> Sequence[SubmittedTask]:
        """Return a bounded task proposal; do not execute tools."""
        ...


class PlanSandbox(Protocol):
    async def validate(
        self, *, goal: str, principal_id: str,
        submissions: tuple[SubmittedTask, ...], iteration: int,
    ) -> SandboxReport:
        """Validate plans/dependencies without executing external effects."""
        ...


class ResultVerifier(Protocol):
    async def verify(
        self, *, goal: str, principal_id: str,
        submissions: tuple[SubmittedTask, ...], results: tuple[object, ...],
        iteration: int,
    ) -> VerificationReport:
        """Verify task outcomes using explicit evidence and bounded inputs."""
        ...


class AutonomyGovernor(Protocol):
    async def authorize_iteration(
        self, *, goal: str, principal_id: str, iteration: int,
        task_count: int, retrying_after_execution: bool,
    ) -> bool:
        """Fail-closed policy decision; false means no execution for this iteration."""
        ...


@dataclass(frozen=True, slots=True)
class AutonomousLoopResult:
    status: str
    goal: str
    iterations: int
    task_count: int
    execution_started: bool
    summary: str
    feedback: tuple[str, ...] = ()


class GovernedAutonomousLoop:
    """Bounded plan → sandbox → authorized execute → verify/reflexion coordinator."""

    def __init__(
        self, *, planner: AutonomousPlanner, sandbox: PlanSandbox,
        verifier: ResultVerifier, governor: AutonomyGovernor,
        task_service: AgentTaskService, event_bus: EventBus | None = None,
        max_iterations: int = 3, max_tasks_per_iteration: int = 8,
        overall_timeout_seconds: float = 300.0,
        allow_retry_after_execution: bool = False,
    ) -> None:
        if max_iterations < 1 or max_tasks_per_iteration < 1:
            raise ValueError("loop and task limits must be positive")
        if overall_timeout_seconds <= 0:
            raise ValueError("overall_timeout_seconds must be positive")
        self._planner = planner
        self._sandbox = sandbox
        self._verifier = verifier
        self._governor = governor
        self._task_service = task_service
        self._event_bus = event_bus
        self._max_iterations = max_iterations
        self._max_tasks = max_tasks_per_iteration
        self._timeout = overall_timeout_seconds
        self._allow_retry_after_execution = allow_retry_after_execution

    async def run(
        self, *, goal: str, principal_id: str, resource_scope: str,
        cancelled=None,
    ) -> AutonomousLoopResult:
        if not goal.strip() or not principal_id.strip() or not resource_scope.strip():
            raise ValueError("goal, principal_id and resource_scope are required")
        started = monotonic()
        feedback: tuple[str, ...] = ()
        total_tasks = 0
        execution_started = False
        retrying_after_execution = False

        for iteration in range(1, self._max_iterations + 1):
            if cancelled is not None and cancelled():
                return self._result("cancelled", goal, iteration - 1, total_tasks,
                                    execution_started, "Cancellation requested", feedback)
            if monotonic() - started >= self._timeout:
                return self._result("timed_out", goal, iteration - 1, total_tasks,
                                    execution_started, "Autonomous loop deadline exceeded", feedback)

            allowed = await self._governor.authorize_iteration(
                goal=goal, principal_id=principal_id, iteration=iteration,
                task_count=0, retrying_after_execution=retrying_after_execution,
            )
            if not allowed:
                self._emit("AutonomyIterationDenied", goal, principal_id, iteration,
                           {"retrying_after_execution": retrying_after_execution})
                return self._result("denied", goal, iteration - 1, total_tasks,
                                    execution_started, "Autonomy Governor denied iteration", feedback)

            self._emit("AutonomyPlanningStarted", goal, principal_id, iteration, {})
            try:
                submissions = tuple(await asyncio.wait_for(
                    self._planner.propose(
                        goal=goal, principal_id=principal_id, resource_scope=resource_scope,
                        iteration=iteration, feedback=feedback,
                    ),
                    timeout=self._remaining(started),
                ))
            except asyncio.TimeoutError:
                return self._result("timed_out", goal, iteration, total_tasks,
                                    execution_started, "Deadline exceeded during planning", feedback)
            if not submissions:
                feedback = ("Planner returned no tasks.",)
                self._emit("AutonomyReflexion", goal, principal_id, iteration,
                           {"feedback": list(feedback)})
                continue
            if len(submissions) > self._max_tasks:
                return self._result("rejected", goal, iteration, total_tasks,
                                    execution_started, "Proposal exceeds task budget",
                                    ("Too many tasks in one iteration.",))
            if any(item.task.principal_id != principal_id for item in submissions):
                return self._result("rejected", goal, iteration, total_tasks,
                                    execution_started, "Cross-principal proposal rejected",
                                    ("Every task must belong to the requesting principal.",))
            if any(item.task.resource_scope != resource_scope for item in submissions):
                return self._result("rejected", goal, iteration, total_tasks,
                                    execution_started, "Resource-scope mismatch",
                                    ("Every task must remain within the requested resource scope.",))
            ids = [item.task.task_id for item in submissions]
            if len(ids) != len(set(ids)):
                return self._result("rejected", goal, iteration, total_tasks,
                                    execution_started, "Duplicate task IDs rejected", ())

            self._emit("AutonomySandboxStarted", goal, principal_id, iteration,
                       {"task_count": len(submissions)})
            try:
                sandbox_report = await asyncio.wait_for(
                    self._sandbox.validate(
                        goal=goal, principal_id=principal_id,
                        submissions=submissions, iteration=iteration,
                    ),
                    timeout=self._remaining(started),
                )
            except asyncio.TimeoutError:
                return self._result("timed_out", goal, iteration, total_tasks,
                                    execution_started, "Deadline exceeded during sandbox validation", feedback)
            if not sandbox_report.accepted:
                feedback = tuple(sandbox_report.findings) or (sandbox_report.summary,)
                self._emit("AutonomyReflexion", goal, principal_id, iteration,
                           {"phase": "sandbox", "feedback": list(feedback)})
                continue

            # Re-check the governor with the actual bounded proposal before execution.
            allowed = await self._governor.authorize_iteration(
                goal=goal, principal_id=principal_id, iteration=iteration,
                task_count=len(submissions), retrying_after_execution=retrying_after_execution,
            )
            if not allowed:
                self._emit("AutonomyIterationDenied", goal, principal_id, iteration,
                           {"phase": "pre_execution"})
                return self._result("denied", goal, iteration, total_tasks,
                                    execution_started, "Governor denied proposed execution", feedback)

            if cancelled is not None and cancelled():
                return self._result("cancelled", goal, iteration, total_tasks,
                                    execution_started, "Cancellation requested before execution", feedback)
            if monotonic() - started >= self._timeout:
                return self._result("timed_out", goal, iteration, total_tasks,
                                    execution_started, "Deadline exceeded before execution", feedback)

            self._emit("AutonomyExecutionStarted", goal, principal_id, iteration,
                       {"task_count": len(submissions)})
            execution_started = True
            total_tasks += len(submissions)
            remaining = self._remaining(started)
            execution_task = asyncio.create_task(self._task_service.submit_chain(submissions))
            try:
                while not execution_task.done():
                    # Polling is only for cooperative cancellation of the loop; the
                    # task runtime still owns tool cancellation and gateway boundaries.
                    done, _ = await asyncio.wait(
                        {execution_task}, timeout=min(0.05, self._remaining(started))
                    )
                    if done:
                        break
                    if cancelled is not None:
                        try:
                            cancel_requested = bool(cancelled())
                        except Exception:
                            cancel_requested = True  # fail closed if cancellation state is unreadable
                        if cancel_requested:
                            execution_task.cancel()
                            await asyncio.gather(execution_task, return_exceptions=True)
                            self._emit("AutonomyExecutionCancelled", goal, principal_id, iteration, {})
                            return self._result("cancelled", goal, iteration, total_tasks,
                                                execution_started, "Cancellation requested during execution", feedback)
                results = await asyncio.wait_for(execution_task, timeout=self._remaining(started))
            except asyncio.CancelledError:
                execution_task.cancel()
                await asyncio.gather(execution_task, return_exceptions=True)
                raise
            except asyncio.TimeoutError:
                execution_task.cancel()
                await asyncio.gather(execution_task, return_exceptions=True)
                return self._result("timed_out", goal, iteration, total_tasks,
                                    execution_started, "Deadline exceeded during task execution", feedback)
            except Exception as exc:
                feedback = (f"Execution failed: {type(exc).__name__}.",)
                self._emit("AutonomyReflexion", goal, principal_id, iteration,
                           {"phase": "execution", "feedback": list(feedback)})
                if not self._allow_retry_after_execution or iteration == self._max_iterations:
                    return self._result("needs_review", goal, iteration, total_tasks,
                                        execution_started, "Execution failed; no automatic replay", feedback)
                retrying_after_execution = True
                continue

            try:
                verification = await asyncio.wait_for(
                    self._verifier.verify(
                        goal=goal, principal_id=principal_id,
                        submissions=submissions, results=tuple(results), iteration=iteration,
                    ),
                    timeout=self._remaining(started),
                )
            except asyncio.TimeoutError:
                return self._result("timed_out", goal, iteration, total_tasks,
                                    execution_started, "Deadline exceeded during verification", feedback)
            if verification.passed:
                self._emit("AutonomyGoalVerified", goal, principal_id, iteration,
                           {"summary": verification.summary})
                return self._result("succeeded", goal, iteration, total_tasks,
                                    execution_started, verification.summary, ())

            feedback = tuple(verification.findings) or (verification.summary,)
            self._emit("AutonomyReflexion", goal, principal_id, iteration,
                       {"phase": "verification", "feedback": list(feedback)})
            if not self._allow_retry_after_execution or iteration == self._max_iterations:
                return self._result("needs_review", goal, iteration, total_tasks,
                                    execution_started,
                                    "Verification failed; automatic replay is disabled", feedback)
            retrying_after_execution = True

        return self._result("exhausted", goal, self._max_iterations, total_tasks,
                            execution_started, "Maximum planning iterations reached", feedback)

    def _remaining(self, started: float) -> float:
        remaining = self._timeout - (monotonic() - started)
        if remaining <= 0:
            raise asyncio.TimeoutError("Autonomous loop deadline exceeded")
        return remaining

    def _emit(
        self, event_type: str, goal: str, principal_id: str, iteration: int,
        extra: dict[str, object],
    ) -> None:
        if self._event_bus is None:
            return
        self._event_bus.publish(KernelEvent(
            event_type=event_type,
            source_component="aura.governed_autonomous_loop",
            correlation_id=f"{principal_id}:{iteration}",
            payload={"goal": goal[:1000], "principal_id": principal_id,
                     "iteration": iteration, **extra},
        ))

    @staticmethod
    def _result(
        status: str, goal: str, iterations: int, task_count: int,
        execution_started: bool, summary: str, feedback: tuple[str, ...],
    ) -> AutonomousLoopResult:
        return AutonomousLoopResult(
            status=status, goal=goal[:1000], iterations=iterations,
            task_count=task_count, execution_started=execution_started,
            summary=summary[:2000], feedback=feedback[:16],
        )
