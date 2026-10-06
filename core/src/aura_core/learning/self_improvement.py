from __future__ import annotations

from dataclasses import dataclass, fields, replace
from enum import StrEnum
from math import isfinite


class ImprovementDecision(StrEnum):
    NOOP = "noop"
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


@dataclass(frozen=True, slots=True)
class LearningMetrics:
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    consecutive_failures: int = 0
    average_runtime_seconds: float = 0.0
    average_queries: float = 0.0
    average_fetches: float = 0.0
    average_new_records: float = 0.0
    admission_rate: float = 1.0
    promotion_rate: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_runs <= 0:
            return 0.0

        return (
            self.successful_runs
            / self.total_runs
        )

    @property
    def failure_rate(self) -> float:
        if self.total_runs <= 0:
            return 0.0

        return (
            self.failed_runs
            / self.total_runs
        )


@dataclass(frozen=True, slots=True)
class PolicyBounds:
    min_queries: int = 1
    max_queries: int = 100
    min_fetches: int = 0
    max_fetches: int = 100
    min_new_records: int = 1
    max_new_records: int = 100
    min_interval_seconds: float = 1.0
    max_interval_seconds: float = 3600.0

    max_step_ratio: float = 0.20
    min_success_rate: float = 0.50
    max_failure_rate: float = 0.50
    max_consecutive_failures: int = 3

    min_sample_size: int = 5

    def validate(self) -> None:
        if self.min_queries < 0:
            raise ValueError(
                "min_queries must be non-negative"
            )

        if self.min_fetches < 0:
            raise ValueError(
                "min_fetches must be non-negative"
            )

        if self.min_new_records < 0:
            raise ValueError(
                "min_new_records must be non-negative"
            )

        if (
            self.max_queries
            < self.min_queries
        ):
            raise ValueError(
                "max_queries must be >= min_queries"
            )

        if (
            self.max_fetches
            < self.min_fetches
        ):
            raise ValueError(
                "max_fetches must be >= min_fetches"
            )

        if (
            self.max_new_records
            < self.min_new_records
        ):
            raise ValueError(
                "max_new_records must be >= min_new_records"
            )

        if (
            self.max_interval_seconds
            < self.min_interval_seconds
        ):
            raise ValueError(
                "max_interval_seconds must be >= min_interval_seconds"
            )

        if not (
            0.0
            < self.max_step_ratio
            <= 1.0
        ):
            raise ValueError(
                "max_step_ratio must be in (0, 1]"
            )

        if not (
            0.0
            <= self.min_success_rate
            <= 1.0
        ):
            raise ValueError(
                "min_success_rate must be in [0, 1]"
            )

        if not (
            0.0
            <= self.max_failure_rate
            <= 1.0
        ):
            raise ValueError(
                "max_failure_rate must be in [0, 1]"
            )


@dataclass(frozen=True, slots=True)
class PolicyChange:
    field_name: str
    old_value: object
    new_value: object
    reason: str


@dataclass(frozen=True, slots=True)
class ImprovementProposal:
    current_policy: object
    candidate_policy: object
    changes: tuple[PolicyChange, ...]
    decision: ImprovementDecision
    reason: str
    metrics: LearningMetrics


@dataclass(frozen=True, slots=True)
class PolicySnapshot:
    policy: object
    metrics: LearningMetrics
    generation: int


class SelfImprovementController:
    """
    Deterministic, bounded policy optimizer.

    The controller can modify LearningPolicy parameters only inside
    PolicyBounds and only by a bounded step.

    It cannot:
      - modify Kernel/PermissionEngine configuration
      - create authorization policies
      - modify providers
      - modify capabilities
      - modify executable code
      - increase limits beyond configured bounds
      - apply changes when evidence is insufficient
      - apply changes while the system is unstable

    Policy updates are pure dataclass replacements. The caller remains
    responsible for installing the accepted policy into the runtime.
    """

    def __init__(
        self,
        *,
        bounds: PolicyBounds | None = None,
    ) -> None:
        self.bounds = (
            bounds
            or PolicyBounds()
        )

        self.bounds.validate()

        self._generation = 0
        self._history: list[
            PolicySnapshot
        ] = []

    @property
    def generation(self) -> int:
        return self._generation

    @staticmethod
    def _finite_float(
        value: object,
        default: float,
    ) -> float:
        try:
            result = float(value)
        except (
            TypeError,
            ValueError,
        ):
            return default

        if not isfinite(result):
            return default

        return result

    @staticmethod
    def _bounded_step(
        current: float,
        target: float,
        ratio: float,
    ) -> float:
        if current <= 0:
            return target

        delta = current * ratio

        if target > current:
            return current + min(
                delta,
                target - current,
            )

        return current - min(
            delta,
            current - target,
        )

    @staticmethod
    def _field_names(
        policy: object,
    ) -> set[str]:
        try:
            return {
                item.name
                for item in fields(policy)
            }
        except TypeError:
            return set()

    def _clamp_int(
        self,
        value: int,
        lower: int,
        upper: int,
    ) -> int:
        return max(
            lower,
            min(upper, value),
        )

    def _clamp_float(
        self,
        value: float,
        lower: float,
        upper: float,
    ) -> float:
        return max(
            lower,
            min(upper, value),
        )

    def _candidate(
        self,
        policy: object,
        metrics: LearningMetrics,
    ) -> tuple[object, tuple[PolicyChange, ...]]:
        names = self._field_names(
            policy
        )

        changes: list[PolicyChange] = []
        candidate = policy

        def change(
            name: str,
            new_value: object,
            reason: str,
        ) -> None:
            nonlocal candidate

            if name not in names:
                return

            old_value = getattr(
                candidate,
                name,
            )

            if old_value == new_value:
                return

            candidate = replace(
                candidate,
                **{
                    name: new_value
                },
            )

            changes.append(
                PolicyChange(
                    field_name=name,
                    old_value=old_value,
                    new_value=new_value,
                    reason=reason,
                )
            )

        unstable = (
            metrics.consecutive_failures
            >= self.bounds.max_consecutive_failures
            or metrics.failure_rate
            > self.bounds.max_failure_rate
        )

        insufficient_evidence = (
            metrics.total_runs
            < self.bounds.min_sample_size
        )

        if insufficient_evidence:
            return (
                policy,
                (),
            )

        if unstable:
            if (
                "max_queries"
                in names
            ):
                current = int(
                    getattr(
                        candidate,
                        "max_queries",
                    )
                )

                target = max(
                    self.bounds.min_queries,
                    int(
                        current
                        * (
                            1.0
                            - self.bounds.max_step_ratio
                        )
                    ),
                )

                change(
                    "max_queries",
                    self._clamp_int(
                        target,
                        self.bounds.min_queries,
                        self.bounds.max_queries,
                    ),
                    "reduce research budget during instability",
                )

            if (
                "max_fetches"
                in names
            ):
                current = int(
                    getattr(
                        candidate,
                        "max_fetches",
                    )
                )

                target = max(
                    self.bounds.min_fetches,
                    int(
                        current
                        * (
                            1.0
                            - self.bounds.max_step_ratio
                        )
                    ),
                )

                change(
                    "max_fetches",
                    self._clamp_int(
                        target,
                        self.bounds.min_fetches,
                        self.bounds.max_fetches,
                    ),
                    "reduce fetch budget during instability",
                )

            if (
                "max_new_records"
                in names
            ):
                current = int(
                    getattr(
                        candidate,
                        "max_new_records",
                    )
                )

                target = max(
                    self.bounds.min_new_records,
                    int(
                        current
                        * (
                            1.0
                            - self.bounds.max_step_ratio
                        )
                    ),
                )

                change(
                    "max_new_records",
                    self._clamp_int(
                        target,
                        self.bounds.min_new_records,
                        self.bounds.max_new_records,
                    ),
                    "reduce memory admission pressure during instability",
                )

            if (
                "interval_seconds"
                in names
            ):
                current = (
                    self._finite_float(
                        getattr(
                            candidate,
                            "interval_seconds",
                        ),
                        self.bounds.min_interval_seconds,
                    )
                )

                target = current * (
                    1.0
                    + self.bounds.max_step_ratio
                )

                change(
                    "interval_seconds",
                    self._clamp_float(
                        target,
                        self.bounds.min_interval_seconds,
                        self.bounds.max_interval_seconds,
                    ),
                    "increase cooldown interval during instability",
                )

        elif (
            metrics.success_rate
            >= self.bounds.min_success_rate
            and metrics.admission_rate >= 0.70
        ):
            if (
                "max_queries"
                in names
            ):
                current = int(
                    getattr(
                        candidate,
                        "max_queries",
                    )
                )

                target = current * (
                    1.0
                    + self.bounds.max_step_ratio
                )

                change(
                    "max_queries",
                    self._clamp_int(
                        int(target),
                        self.bounds.min_queries,
                        self.bounds.max_queries,
                    ),
                    "increase research budget after stable success",
                )

            if (
                "max_fetches"
                in names
            ):
                current = int(
                    getattr(
                        candidate,
                        "max_fetches",
                    )
                )

                target = current * (
                    1.0
                    + self.bounds.max_step_ratio
                )

                change(
                    "max_fetches",
                    self._clamp_int(
                        int(target),
                        self.bounds.min_fetches,
                        self.bounds.max_fetches,
                    ),
                    "increase fetch budget after stable success",
                )

            if (
                "interval_seconds"
                in names
            ):
                current = (
                    self._finite_float(
                        getattr(
                            candidate,
                            "interval_seconds",
                        ),
                        self.bounds.min_interval_seconds,
                    )
                )

                target = current * (
                    1.0
                    - self.bounds.max_step_ratio
                )

                change(
                    "interval_seconds",
                    self._clamp_float(
                        target,
                        self.bounds.min_interval_seconds,
                        self.bounds.max_interval_seconds,
                    ),
                    "reduce idle interval after stable success",
                )

        return (
            candidate,
            tuple(changes),
        )

    def propose(
        self,
        policy: object,
        metrics: LearningMetrics,
    ) -> ImprovementProposal:
        candidate, changes = (
            self._candidate(
                policy,
                metrics,
            )
        )

        if not changes:
            return ImprovementProposal(
                current_policy=policy,
                candidate_policy=policy,
                changes=(),
                decision=ImprovementDecision.NOOP,
                reason=(
                    "No bounded improvement justified "
                    "by current evidence."
                ),
                metrics=metrics,
            )

        return ImprovementProposal(
            current_policy=policy,
            candidate_policy=candidate,
            changes=changes,
            decision=ImprovementDecision.PROPOSED,
            reason=(
                "Candidate policy remains inside "
                "deterministic safety bounds."
            ),
            metrics=metrics,
        )

    def accept(
        self,
        proposal: ImprovementProposal,
    ) -> ImprovementProposal:
        if (
            proposal.decision
            is not ImprovementDecision.PROPOSED
        ):
            return proposal

        self._generation += 1

        self._history.append(
            PolicySnapshot(
                policy=proposal.candidate_policy,
                metrics=proposal.metrics,
                generation=self._generation,
            )
        )

        return ImprovementProposal(
            current_policy=proposal.current_policy,
            candidate_policy=proposal.candidate_policy,
            changes=proposal.changes,
            decision=ImprovementDecision.ACCEPTED,
            reason=(
                "Bounded policy proposal accepted."
            ),
            metrics=proposal.metrics,
        )

    def reject(
        self,
        proposal: ImprovementProposal,
        *,
        reason: str = "proposal rejected",
    ) -> ImprovementProposal:
        return ImprovementProposal(
            current_policy=proposal.current_policy,
            candidate_policy=proposal.current_policy,
            changes=proposal.changes,
            decision=ImprovementDecision.REJECTED,
            reason=reason,
            metrics=proposal.metrics,
        )

    def rollback(
        self,
        current_policy: object,
    ) -> ImprovementProposal | None:
        if not self._history:
            return None

        previous = self._history[-1]

        self._history.pop()

        return ImprovementProposal(
            current_policy=current_policy,
            candidate_policy=previous.policy,
            changes=(),
            decision=ImprovementDecision.ROLLED_BACK,
            reason=(
                "Rolled back to the previous accepted "
                "policy snapshot."
            ),
            metrics=previous.metrics,
        )

    def history(
        self,
    ) -> tuple[PolicySnapshot, ...]:
        return tuple(
            self._history
        )

    def snapshot(
        self,
    ) -> dict[str, object]:
        return {
            "generation": self._generation,
            "history_size": len(
                self._history
            ),
            "bounds": self.bounds,
        }
