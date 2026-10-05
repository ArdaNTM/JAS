from __future__ import annotations

import asyncio
import logging

from .models import LearningObjective
from aura_core.learning.models import LearningStatus

logger = logging.getLogger(__name__)


class ContinuousLearningScheduler:
    def __init__(
        self,
        *,
        engine,
        objectives,
        interval_seconds: float | None = None,
    ) -> None:
        self.engine = engine
        self.objectives = list(objectives)

        self.interval_seconds = (
            interval_seconds
            if interval_seconds is not None
            else engine.policy.interval_seconds
        )

        if self.interval_seconds <= 0:
            raise ValueError(
                "interval_seconds must be positive"
            )

        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    @property
    def running(self) -> bool:
        return (
            self._task is not None
            and not self._task.done()
        )

    async def start(self) -> None:
        if self.running:
            return

        self._stop.clear()

        self._task = asyncio.create_task(
            self._run(),
            name="aura-continuous-learning",
        )

    async def stop(self) -> None:
        self._stop.set()

        task = self._task
        self._task = None

        if task is not None:
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while not self._stop.is_set():
            objectives = sorted(
                (
                    objective
                    for objective in self.objectives
                    if objective.enabled
                ),
                key=lambda objective: (
                    -objective.priority,
                    objective.objective_id,
                ),
            )

            for objective in objectives:
                if self._stop.is_set():
                    break

                try:
                    result = await self.engine.run(
                        objective
                    )

                    if result.status is LearningStatus.FAILED:
                        logger.error(
                            "Autonomous learning cycle failed: %s: %s",
                            objective.objective_id,
                            result.error,
                        )
                    elif result.status is LearningStatus.STOPPED:
                        logger.warning(
                            "Autonomous learning cycle stopped: %s: %s",
                            objective.objective_id,
                            result.error,
                        )

                except Exception:
                    logger.exception(
                        "Autonomous learning cycle raised an exception: %s",
                        objective.objective_id,
                    )

            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self.interval_seconds,
                )
            except asyncio.TimeoutError:
                pass
