from __future__ import annotations

import asyncio
from pathlib import Path

from aura_core.learning.skill_library import (
    SkillExtractor,
    SkillLibrary,
)
from aura_core.learning.skill_validation import (
    SkillPromotionManager,
    SkillPromotionPolicy,
)


async def main() -> None:
    root = Path(".aura/phase8-skill-test")

    library = SkillLibrary(root)
    await library.initialize()

    skill = SkillExtractor.from_run(
        run_id="phase8-test-run-001",
        objective="Research Model Context Protocol",
        capability_id="internet.search",
        operation_id="internet.search",
        tool_name="search",
        success=True,
        confidence=0.95,
    )

    if skill is None:
        raise RuntimeError(
            "SkillExtractor returned no skill"
        )

    skill.record_success(
        "phase8-test-run-001"
    )

    await library.register(skill)

    manager = SkillPromotionManager(
        library,
        policy=SkillPromotionPolicy(
            min_confidence=0.80,
            min_success_rate=0.80,
            min_success_count=1,
            min_validation_score=0.85,
        ),
    )

    result = await manager.consider(
        skill
    )

    if not result.valid:
        raise RuntimeError(
            f"Skill validation failed: {result}"
        )

    print(
        "Phase 8 skill integration smoke test passed."
    )


asyncio.run(main())
