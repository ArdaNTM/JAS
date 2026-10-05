from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class LearningStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass(slots=True)
class LearningObjective:
    objective_id: str
    title: str
    description: str
    namespace: str = "default"
    priority: int = 0
    enabled: bool = True


@dataclass(slots=True)
class LearningPolicy:
    interval_seconds: float = 300.0
    max_sources: int = 8
    max_steps: int = 16
    max_iterations: int = 4
    max_runtime_seconds: float = 180.0
    max_content_chars: int = 200_000
    idle_sleep_seconds: float = 5.0


@dataclass(slots=True)
class LearningRun:
    run_id: str
    objective_id: str
    status: LearningStatus = LearningStatus.IDLE
    steps: int = 0
    sources: int = 0
    records: int = 0
    facts: int = 0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
