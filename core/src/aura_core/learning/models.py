from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum


class LearningStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    COOLDOWN = "cooldown"
    FAILED = "failed"
    COMPLETED = "completed"
    STOPPED = "stopped"


@dataclass(slots=True)
class LearningObjective:
    objective_id: str
    description: str
    title: str | None = None
    priority: int = 0
    enabled: bool = True


@dataclass(slots=True)
class LearningPolicy:
    interval_seconds: float = 300.0
    max_sources: int = 8
    max_steps: int = 16
    max_iterations: int = 4
    max_runtime_seconds: float = 180.0
    max_consecutive_failures: int = 3
    cooldown_seconds: float = 300.0
    max_budget_units: int = 100
    max_queries: int = 16
    max_fetches: int = 32
    max_new_records: int = 32


@dataclass(slots=True)
class LearningBudget:
    units: int
    queries: int = 0
    fetches: int = 0
    new_records: int = 0

    def can_spend(self, amount: int = 1) -> bool:
        return amount >= 0 and self.units >= amount

    def spend(self, amount: int = 1) -> None:
        if amount < 0:
            raise ValueError("Budget amount cannot be negative")
        if not self.can_spend(amount):
            raise RuntimeError("Learning budget exhausted")
        self.units -= amount


@dataclass(slots=True)
class LearningRuntimeState:
    run_id: str
    objective_id: str
    status: LearningStatus = LearningStatus.IDLE
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cooldown_until: datetime | None = None
    consecutive_failures: int = 0
    total_failures: int = 0
    total_successes: int = 0
    iteration: int = 0
    steps: int = 0
    sources: int = 0
    records: int = 0
    budget: LearningBudget = field(
        default_factory=lambda: LearningBudget(units=100)
    )
    last_error: str | None = None

    def start(self) -> None:
        if self.status is LearningStatus.RUNNING:
            raise RuntimeError(
                f"Learning run already running: {self.run_id}"
            )
        if self.in_cooldown():
            raise RuntimeError(
                f"Learning run is in cooldown: {self.run_id}"
            )
        self.status = LearningStatus.RUNNING
        self.started_at = datetime.now(UTC)
        self.completed_at = None
        self.last_error = None

    def succeed(self) -> None:
        self.status = LearningStatus.COMPLETED
        self.completed_at = datetime.now(UTC)
        self.consecutive_failures = 0
        self.total_successes += 1
        self.cooldown_until = None

    def fail(
        self,
        error: str,
        *,
        cooldown_seconds: float,
        max_consecutive_failures: int,
    ) -> None:
        self.status = LearningStatus.FAILED
        self.completed_at = datetime.now(UTC)
        self.last_error = error
        self.consecutive_failures += 1
        self.total_failures += 1

        if self.consecutive_failures >= max_consecutive_failures:
            self.status = LearningStatus.COOLDOWN
            self.cooldown_until = (
                datetime.now(UTC)
                + timedelta(seconds=cooldown_seconds)
            )

    def stop(self) -> None:
        self.status = LearningStatus.STOPPED
        self.completed_at = datetime.now(UTC)

    def in_cooldown(self) -> bool:
        if self.cooldown_until is None:
            return False
        return datetime.now(UTC) < self.cooldown_until

    def next_iteration(self) -> None:
        self.iteration += 1

    def consume_step(self) -> None:
        self.steps += 1

    def consume_source(self) -> None:
        self.sources += 1

    def consume_record(self) -> None:
        self.records += 1

    def snapshot(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "objective_id": self.objective_id,
            "status": self.status.value,
            "started_at": (
                self.started_at.isoformat()
                if self.started_at
                else None
            ),
            "completed_at": (
                self.completed_at.isoformat()
                if self.completed_at
                else None
            ),
            "cooldown_until": (
                self.cooldown_until.isoformat()
                if self.cooldown_until
                else None
            ),
            "consecutive_failures": self.consecutive_failures,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "iteration": self.iteration,
            "steps": self.steps,
            "sources": self.sources,
            "records": self.records,
            "budget": {
                "units": self.budget.units,
                "queries": self.budget.queries,
                "fetches": self.budget.fetches,
                "new_records": self.budget.new_records,
            },
            "last_error": self.last_error,
        }


@dataclass(slots=True)
class LearningRun:
    run_id: str
    objective_id: str
    status: LearningStatus
    steps: int = 0
    sources: int = 0
    records: int = 0
    error: str | None = None
