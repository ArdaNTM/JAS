from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from .models import LearningObjective, LearningStatus

logger = logging.getLogger(__name__)


class ContinuousLearningScheduler:
    def __init__(
        self,
        *,
        engine,
        objectives,
        interval_seconds: float | None = None,
        skill_library=None,
        skill_promotion_manager=None,
        skill_extractor=None,
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

        self.skill_library = skill_library
        self.skill_promotion_manager = (
            skill_promotion_manager
        )
        self.skill_extractor = skill_extractor

        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._skill_lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return (
            self._task is not None
            and not self._task.done()
        )

    async def start(self) -> None:
        if self.running:
            return

        if self.skill_library is not None:
            await self.skill_library.initialize()

        self._stop.clear()

        self._task = asyncio.create_task(
            self._run(),
            name="aura-continuous-learning",
        )

        logger.info(
            "Continuous learning scheduler started"
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

        logger.info(
            "Continuous learning scheduler stopped"
        )

    def _ordered_objectives(
        self,
    ) -> list[LearningObjective]:
        return sorted(
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

    def _extract_tool_context(
        self,
    ) -> tuple[str, str, str]:
        spec = getattr(
            self.engine,
            "tool_spec",
            None,
        )

        if spec is None:
            return (
                "",
                "",
                "",
            )

        return (
            str(
                getattr(
                    spec,
                    "search_capability_id",
                    "",
                )
            ),
            str(
                getattr(
                    spec,
                    "search_operation_id",
                    "",
                )
            ),
            str(
                getattr(
                    spec,
                    "search_tool_name",
                    "",
                )
            ),
        )

    async def _promote_successful_run(
        self,
        objective: LearningObjective,
        result: Any,
    ) -> None:
        if (
            self.skill_library is None
            or self.skill_extractor is None
            or self.skill_promotion_manager is None
        ):
            return

        if (
            getattr(
                result,
                "status",
                None,
            )
            is not LearningStatus.COMPLETED
        ):
            return

        run_id = str(
            getattr(
                result,
                "run_id",
                "",
            )
        )

        if not run_id:
            return

        capability_id, operation_id, tool_name = (
            self._extract_tool_context()
        )

        if not (
            capability_id
            and operation_id
            and tool_name
        ):
            logger.warning(
                "Skill extraction skipped: "
                "research tool specification is incomplete"
            )
            return

        async with self._skill_lock:
            skill = self.skill_extractor.from_run(
                run_id=run_id,
                objective=objective.description,
                capability_id=capability_id,
                operation_id=operation_id,
                tool_name=tool_name,
                success=True,
                confidence=0.7,
            )

            if skill is None:
                return

            existing = await self.skill_library.get(
                skill.skill_id
            )

            if existing is not None:
                source_run_ids = set(
                    existing.source_run_ids
                )

                if run_id in source_run_ids:
                    logger.debug(
                        "Skill already credited for run: %s",
                        run_id,
                    )
                    return

                await self.skill_library.record_success(
                    skill.skill_id,
                    run_id=run_id,
                )

                skill = await self.skill_library.get(
                    skill.skill_id
                )

                if skill is None:
                    return

            else:
                skill.record_success(
                    run_id
                )

                await self.skill_library.register(
                    skill
                )

            validation = (
                await self.skill_promotion_manager.consider(
                    skill
                )
            )

            logger.info(
                "Skill lifecycle: skill=%s lifecycle=%s "
                "score=%.3f success_rate=%.3f",
                skill.skill_id,
                validation.lifecycle.value,
                validation.score,
                skill.success_rate,
            )

    async def _record_failed_skill_feedback(
        self,
        objective: LearningObjective,
        result: Any,
    ) -> None:
        if (
            self.skill_library is None
            or self.skill_extractor is None
        ):
            return

        if (
            getattr(
                result,
                "status",
                None,
            )
            is not LearningStatus.FAILED
        ):
            return

        capability_id, operation_id, tool_name = (
            self._extract_tool_context()
        )

        if not (
            capability_id
            and operation_id
            and tool_name
        ):
            return

        run_id = str(
            getattr(
                result,
                "run_id",
                "",
            )
        )

        if not run_id:
            return

        skill = self.skill_extractor.from_run(
            run_id=run_id,
            objective=objective.description,
            capability_id=capability_id,
            operation_id=operation_id,
            tool_name=tool_name,
            success=True,
            confidence=0.3,
        )

        if skill is None:
            return

        existing = await self.skill_library.get(
            skill.skill_id
        )

        if existing is None:
            return

        if run_id in set(
            existing.source_run_ids
        ):
            return

        await self.skill_library.record_failure(
            skill.skill_id,
            run_id=run_id,
        )

        logger.info(
            "Recorded skill failure feedback: %s",
            skill.skill_id,
        )

    async def _run_objective(
        self,
        objective: LearningObjective,
    ) -> None:
        if self._stop.is_set():
            return

        try:
            result = await self.engine.run(
                objective
            )

            status = getattr(
                result,
                "status",
                None,
            )

            if status is LearningStatus.COMPLETED:
                logger.info(
                    "Autonomous learning cycle completed: %s",
                    objective.objective_id,
                )

                await self._promote_successful_run(
                    objective,
                    result,
                )

            elif status is LearningStatus.FAILED:
                logger.error(
                    "Autonomous learning cycle failed: %s: %s",
                    objective.objective_id,
                    getattr(
                        result,
                        "error",
                        None,
                    ),
                )

                await self._record_failed_skill_feedback(
                    objective,
                    result,
                )

            elif status is LearningStatus.STOPPED:
                logger.warning(
                    "Autonomous learning cycle stopped: %s: %s",
                    objective.objective_id,
                    getattr(
                        result,
                        "error",
                        None,
                    ),
                )

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "Autonomous learning cycle raised: %s",
                objective.objective_id,
            )

    async def _run(self) -> None:
        logger.info(
            "Continuous learning background loop entered"
        )

        try:
            while not self._stop.is_set():
                objectives = self._ordered_objectives()

                for objective in objectives:
                    if self._stop.is_set():
                        break

                    await self._run_objective(
                        objective
                    )

                if self._stop.is_set():
                    break

                try:
                    await asyncio.wait_for(
                        self._stop.wait(),
                        timeout=self.interval_seconds,
                    )
                except asyncio.TimeoutError:
                    pass

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "Fatal scheduler loop error"
            )

        finally:
            logger.info(
                "Continuous learning background loop exited"
            )

    async def snapshot(
        self,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "running": self.running,
            "interval_seconds": self.interval_seconds,
            "objectives": len(
                self.objectives
            ),
            "skill_integration": (
                self.skill_library is not None
                and self.skill_promotion_manager is not None
                and self.skill_extractor is not None
            ),
        }

        if self.skill_library is not None:
            payload[
                "skill_library"
            ] = await self.skill_library.snapshot()

        return payload
