from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from aura_core.learning.models import (
    LearningObjective,
    LearningRun,
    LearningStatus,
)
from aura_core.learning.scheduler import (
    ContinuousLearningScheduler,
)
from aura_core.learning.skill_library import (
    SkillExtractor,
    SkillLibrary,
)
from aura_core.learning.skill_validation import (
    SkillLifecycle,
    SkillPromotionManager,
    SkillPromotionPolicy,
    SkillValidator,
)


class FakePolicy:
    interval_seconds = 0.01


class FakeToolSpec:
    search_capability_id = "internet.search"
    search_operation_id = "internet.search"
    search_tool_name = "search"


class FakeEngine:
    def __init__(
        self,
        *,
        fail: bool = False,
    ) -> None:
        self.policy = FakePolicy()
        self.tool_spec = FakeToolSpec()
        self.fail = fail
        self.calls: list[str] = []

    async def run(
        self,
        objective: LearningObjective,
    ) -> LearningRun:
        self.calls.append(
            objective.objective_id
        )

        status = (
            LearningStatus.FAILED
            if self.fail
            else LearningStatus.COMPLETED
        )

        run = LearningRun(
            run_id=f"run:{objective.objective_id}",
            objective_id=objective.objective_id,
            status=status,
        )

        if self.fail:
            run.error = (
                "deterministic injected failure"
            )

        return run


class ReflectionHarness:
    def __init__(self) -> None:
        self.reflections: list[str] = []

    async def reflect(
        self,
        *,
        run: LearningRun,
    ) -> str:
        if run.status is LearningStatus.COMPLETED:
            value = (
                "Successful research workflow should "
                "be reusable after validation."
            )
        else:
            value = (
                "Failed research workflow must not "
                "be promoted."
            )

        self.reflections.append(value)
        return value


class CriticHarness:
    def __init__(self) -> None:
        self.calls = 0

    async def critique(
        self,
        value: str,
    ) -> str:
        self.calls += 1
        return f"critic-reviewed:{value}"


class RefinerHarness:
    def __init__(self) -> None:
        self.calls = 0

    async def refine(
        self,
        value: str,
    ) -> str:
        self.calls += 1
        return f"refined:{value}"


@pytest.fixture
def objective() -> LearningObjective:
    return LearningObjective(
        objective_id="e2e-objective-001",
        title="Research MCP",
        description=(
            "Research Model Context Protocol "
            "and produce reusable evidence."
        ),
        priority=100,
        enabled=True,
    )


def test_phase9_skill_lifecycle_end_to_end(
    tmp_path: Path,
    objective: LearningObjective,
) -> None:
    asyncio.run(
        _phase9_skill_lifecycle_end_to_end(
            tmp_path,
            objective,
        )
    )


async def _phase9_skill_lifecycle_end_to_end(
    tmp_path: Path,
    objective: LearningObjective,
) -> None:
    engine = FakeEngine()

    library = SkillLibrary(
        tmp_path / "skills"
    )

    await library.initialize()

    extractor = SkillExtractor()

    policy = SkillPromotionPolicy(
        min_confidence=0.80,
        min_success_rate=0.80,
        min_success_count=1,
        min_validation_score=0.85,
    )

    promoter = SkillPromotionManager(
        library,
        validator=SkillValidator(
            policy=policy
        ),
        policy=policy,
    )

    scheduler = ContinuousLearningScheduler(
        engine=engine,
        objectives=[objective],
        interval_seconds=0.01,
        skill_library=library,
        skill_promotion_manager=promoter,
        skill_extractor=extractor,
    )

    reflection = ReflectionHarness()
    critic = CriticHarness()
    refiner = RefinerHarness()

    await scheduler.start()

    try:
        for _ in range(100):
            if engine.calls:
                break
            await asyncio.sleep(0.005)

        assert engine.calls == [
            objective.objective_id
        ]

        run = await engine.run(
            objective
        )

        reflection_text = await reflection.reflect(
            run=run
        )

        assert reflection.reflections
        assert "reusable" in reflection_text

        criticized = await critic.critique(
            reflection_text
        )

        refined = await refiner.refine(
            criticized
        )

        assert critic.calls == 1
        assert refiner.calls == 1
        assert refined.startswith(
            "refined:"
        )

        skill = extractor.from_run(
            run_id=run.run_id,
            objective=objective.description,
            capability_id=(
                engine.tool_spec.search_capability_id
            ),
            operation_id=(
                engine.tool_spec.search_operation_id
            ),
            tool_name=(
                engine.tool_spec.search_tool_name
            ),
            success=True,
            confidence=0.95,
        )

        assert skill is not None

        skill.record_success(
            run.run_id
        )

        await library.register(
            skill
        )

        validation = await promoter.consider(
            skill
        )

        assert validation.valid
        assert (
            validation.lifecycle
            is SkillLifecycle.PROMOTED
        )

        promoted = await library.get(
            skill.skill_id
        )

        assert promoted is not None
        assert promoted.enabled is True
        assert promoted.success_count >= 1
        assert promoted.confidence >= 0.80
        assert promoted.success_rate >= 0.80

        matches = await library.search(
            "research Model Context Protocol"
        )

        assert matches
        assert matches[0].skill.skill_id == (
            skill.skill_id
        )

    finally:
        await scheduler.stop()


def test_phase9_failed_run_never_promotes(
    tmp_path: Path,
    objective: LearningObjective,
) -> None:
    asyncio.run(
        _phase9_failed_run_never_promotes(
            tmp_path,
            objective,
        )
    )


async def _phase9_failed_run_never_promotes(
    tmp_path: Path,
    objective: LearningObjective,
) -> None:
    engine = FakeEngine(
        fail=True
    )

    library = SkillLibrary(
        tmp_path / "skills"
    )

    await library.initialize()

    extractor = SkillExtractor()

    policy = SkillPromotionPolicy(
        min_confidence=0.80,
        min_success_rate=0.80,
        min_success_count=1,
        min_validation_score=0.85,
    )

    promoter = SkillPromotionManager(
        library,
        validator=SkillValidator(
            policy=policy
        ),
        policy=policy,
    )

    scheduler = ContinuousLearningScheduler(
        engine=engine,
        objectives=[objective],
        interval_seconds=0.01,
        skill_library=library,
        skill_promotion_manager=promoter,
        skill_extractor=extractor,
    )

    await scheduler.start()

    try:
        for _ in range(100):
            if engine.calls:
                break
            await asyncio.sleep(0.005)

        assert engine.calls

        failed = await engine.run(
            objective
        )

        assert (
            failed.status
            is LearningStatus.FAILED
        )

        skill = extractor.from_run(
            run_id=failed.run_id,
            objective=objective.description,
            capability_id=(
                engine.tool_spec.search_capability_id
            ),
            operation_id=(
                engine.tool_spec.search_operation_id
            ),
            tool_name=(
                engine.tool_spec.search_tool_name
            ),
            success=False,
            confidence=0.2,
        )

        assert skill is None
        assert await library.list() == []

    finally:
        await scheduler.stop()


def test_phase9_low_confidence_skill_is_quarantined(
    tmp_path: Path,
    objective: LearningObjective,
) -> None:
    asyncio.run(
        _phase9_low_confidence_skill_is_quarantined(
            tmp_path,
            objective,
        )
    )


async def _phase9_low_confidence_skill_is_quarantined(
    tmp_path: Path,
    objective: LearningObjective,
) -> None:
    library = SkillLibrary(
        tmp_path / "skills"
    )

    await library.initialize()

    extractor = SkillExtractor()

    policy = SkillPromotionPolicy(
        min_confidence=0.90,
        min_success_rate=0.90,
        min_success_count=2,
        min_validation_score=0.85,
    )

    promoter = SkillPromotionManager(
        library,
        validator=SkillValidator(
            policy=policy
        ),
        policy=policy,
    )

    skill = extractor.from_run(
        run_id="weak-run-001",
        objective=objective.description,
        capability_id="internet.search",
        operation_id="internet.search",
        tool_name="search",
        success=True,
        confidence=0.50,
    )

    assert skill is not None

    await library.register(
        skill
    )

    result = await promoter.consider(
        skill
    )

    assert result.lifecycle in {
        SkillLifecycle.VALIDATED,
        SkillLifecycle.QUARANTINED,
    }

    stored = await library.get(
        skill.skill_id
    )

    assert stored is not None
    assert stored.enabled is False


def test_phase9_scheduler_shutdown_is_graceful(
    tmp_path: Path,
    objective: LearningObjective,
) -> None:
    asyncio.run(
        _phase9_scheduler_shutdown_is_graceful(
            tmp_path,
            objective,
        )
    )


async def _phase9_scheduler_shutdown_is_graceful(
    tmp_path: Path,
    objective: LearningObjective,
) -> None:
    engine = FakeEngine()

    library = SkillLibrary(
        tmp_path / "skills"
    )

    await library.initialize()

    policy = SkillPromotionPolicy(
        min_confidence=0.80,
        min_success_rate=0.80,
        min_success_count=1,
    )

    scheduler = ContinuousLearningScheduler(
        engine=engine,
        objectives=[objective],
        interval_seconds=60.0,
        skill_library=library,
        skill_promotion_manager=(
            SkillPromotionManager(
                library,
                policy=policy,
            )
        ),
        skill_extractor=SkillExtractor(),
    )

    await scheduler.start()

    assert scheduler.running

    await scheduler.stop()

    assert not scheduler.running

    await scheduler.stop()

    assert not scheduler.running


def test_phase9_skill_persistence_and_reload(
    tmp_path: Path,
    objective: LearningObjective,
) -> None:
    asyncio.run(
        _phase9_skill_persistence_and_reload(
            tmp_path,
            objective,
        )
    )


async def _phase9_skill_persistence_and_reload(
    tmp_path: Path,
    objective: LearningObjective,
) -> None:
    root = tmp_path / "persistent-skills"

    first = SkillLibrary(root)
    await first.initialize()

    skill = SkillExtractor.from_run(
        run_id="persist-run-001",
        objective=objective.description,
        capability_id="internet.search",
        operation_id="internet.search",
        tool_name="search",
        success=True,
        confidence=0.95,
    )

    assert skill is not None

    skill.record_success(
        "persist-run-001"
    )

    await first.register(
        skill
    )

    second = SkillLibrary(root)
    await second.initialize()

    restored = await second.get(
        skill.skill_id
    )

    assert restored is not None
    assert restored.skill_id == (
        skill.skill_id
    )
    assert restored.success_count == (
        skill.success_count
    )
    assert restored.confidence == (
        skill.confidence
    )
    assert restored.enabled is False


def test_phase9_deterministic_skill_identity(
    objective: LearningObjective,
) -> None:
    asyncio.run(
        _phase9_deterministic_skill_identity(
            objective
        )
    )


async def _phase9_deterministic_skill_identity(
    objective: LearningObjective,
) -> None:
    first = SkillExtractor.from_run(
        run_id="run-a",
        objective=objective.description,
        capability_id="internet.search",
        operation_id="internet.search",
        tool_name="search",
        success=True,
    )

    second = SkillExtractor.from_run(
        run_id="run-b",
        objective=objective.description,
        capability_id="internet.search",
        operation_id="internet.search",
        tool_name="search",
        success=True,
    )

    assert first is not None
    assert second is not None

    assert first.skill_id == (
        second.skill_id
    )
    assert first.name == (
        second.name
    )
    assert first.description == (
        second.description
    )
