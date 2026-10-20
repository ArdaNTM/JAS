"""Bounded recovery policy for multi-step reasoning execution.

This controller returns decisions only. It does not retry or dispatch tools;
the caller must submit every permitted action through AgentTaskService/MCPGateway.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RecoveryAction(StrEnum):
    CONTINUE = "continue"
    REPLAN_ONCE = "replan_once"
    STOP = "stop"
    REQUIRE_APPROVAL = "require_approval"


@dataclass(frozen=True, slots=True)
class StepObservation:
    step_id: str
    succeeded: bool
    retryable: bool = False
    side_effecting: bool = False
    authorization_denied: bool = False
    evidence_count: int = 0


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    action: RecoveryAction
    reason: str
    replan_count: int


class AdaptiveExecutionController:
    """Choose deterministic recovery decisions under a strict replan budget."""

    def __init__(self, max_replans: int = 1) -> None:
        if not 0 <= max_replans <= 2:
            raise ValueError("max_replans must be between 0 and 2")
        self._max_replans = max_replans

    def decide(
        self,
        observation: StepObservation,
        *,
        replan_count: int,
    ) -> RecoveryDecision:
        if replan_count < 0 or replan_count > self._max_replans:
            raise ValueError("replan_count exceeds configured budget")
        if observation.authorization_denied:
            return RecoveryDecision(
                RecoveryAction.STOP,
                "Authorization was denied; policy decisions cannot be bypassed by replanning.",
                replan_count,
            )
        if observation.succeeded:
            if observation.evidence_count == 0:
                return RecoveryDecision(
                    RecoveryAction.REPLAN_ONCE if replan_count < self._max_replans else RecoveryAction.STOP,
                    "The step succeeded but returned no evidence.",
                    replan_count + (1 if replan_count < self._max_replans else 0),
                )
            return RecoveryDecision(RecoveryAction.CONTINUE, "Step succeeded with evidence.", replan_count)
        if observation.side_effecting:
            return RecoveryDecision(
                RecoveryAction.REQUIRE_APPROVAL,
                "Failed side-effecting steps are never retried automatically.",
                replan_count,
            )
        if observation.retryable and replan_count < self._max_replans:
            return RecoveryDecision(
                RecoveryAction.REPLAN_ONCE,
                "Retryable failure permits one bounded replan.",
                replan_count + 1,
            )
        return RecoveryDecision(RecoveryAction.STOP, "Failure is not safely recoverable within budget.", replan_count)
