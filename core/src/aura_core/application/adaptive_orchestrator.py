"""Small bounded retry loop for governed AgentTaskService submissions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from aura_core.agent.runtime import ExecutionResult, Plan, Task
from aura_core.application.adaptive_execution import (
    AdaptiveExecutionController,
    RecoveryAction,
    StepObservation,
)
from aura_core.application.tasks import AgentTaskService, SubmittedTask


@dataclass(frozen=True, slots=True)
class AdaptiveTaskRun:
    execution: ExecutionResult
    task_id: str
    recovery: tuple[dict[str, object], ...]


class AdaptiveTaskOrchestrator:
    """Retry only clearly transient transport failures; every attempt is a new task."""

    def __init__(self, max_replans: int = 1) -> None:
        self._controller = AdaptiveExecutionController(max_replans=max_replans)

    async def run(
        self,
        task_service: AgentTaskService,
        task_factory: Callable[[int], Task],
        plan_factory: Callable[[Task, int], Plan],
        *,
        request_id: str | None,
    ) -> AdaptiveTaskRun:
        replan_count = 0
        decisions: list[dict[str, object]] = []
        while True:
            task = task_factory(replan_count)
            plan = plan_factory(task, replan_count)
            try:
                result = await task_service.submit(
                    SubmittedTask(task, plan, request_id)
                )
            except (TimeoutError, ConnectionError, OSError) as exc:
                decision = self._controller.decide(
                    StepObservation(
                        step_id="research",
                        succeeded=False,
                        retryable=True,
                    ),
                    replan_count=replan_count,
                )
                decisions.append({
                    "action": decision.action.value,
                    "reason": decision.reason,
                    "attempt": replan_count + 1,
                    "error_type": type(exc).__name__,
                })
                if decision.action is RecoveryAction.REPLAN_ONCE:
                    replan_count = decision.replan_count
                    continue
                raise

            failed = result.state.value != "succeeded"
            failure_reason = " ".join(
                step.reason for step in result.steps if step.reason
            )
            lowered = failure_reason.casefold()
            denied = failed and any(
                token in lowered
                for token in ("denied", "not authorized", "authorization", "permission", "approval required")
            )
            has_evidence = any(step.result is not None for step in result.steps)
            decision = self._controller.decide(
                StepObservation(
                    step_id="research",
                    succeeded=not failed,
                    retryable=False,
                    authorization_denied=denied,
                    evidence_count=1 if has_evidence else 0,
                ),
                replan_count=replan_count,
            )
            decisions.append({
                "action": decision.action.value,
                "reason": decision.reason,
                "attempt": replan_count + 1,
                "authorization_denied": denied,
            })
            if decision.action is RecoveryAction.REPLAN_ONCE:
                replan_count = decision.replan_count
                continue
            return AdaptiveTaskRun(
                execution=result,
                task_id=task.task_id,
                recovery=tuple(decisions),
            )
