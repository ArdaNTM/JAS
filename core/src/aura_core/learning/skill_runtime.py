from __future__ import annotations

import os
from pathlib import Path


def create_skill_runtime(
    *,
    engine,
    objectives,
):
    from .skill_library import (
        SkillExtractor,
        SkillLibrary,
    )
    from .skill_validation import (
        SkillPromotionManager,
        SkillPromotionPolicy,
        SkillValidator,
    )
    from .scheduler import (
        ContinuousLearningScheduler,
    )

    root = Path(
        os.getenv(
            "AURA_SKILL_LIBRARY_PATH",
            ".aura/skills",
        )
    )

    library = SkillLibrary(
        root
    )

    policy = SkillPromotionPolicy(
        min_confidence=float(
            os.getenv(
                "AURA_SKILL_MIN_CONFIDENCE",
                "0.80",
            )
        ),
        min_success_rate=float(
            os.getenv(
                "AURA_SKILL_MIN_SUCCESS_RATE",
                "0.80",
            )
        ),
        min_success_count=int(
            os.getenv(
                "AURA_SKILL_MIN_SUCCESS_COUNT",
                "2",
            )
        ),
        min_validation_score=float(
            os.getenv(
                "AURA_SKILL_MIN_VALIDATION_SCORE",
                "0.85",
            )
        ),
        require_replay=(
            os.getenv(
                "AURA_SKILL_REQUIRE_REPLAY",
                "0",
            ).lower()
            in {
                "1",
                "true",
                "yes",
                "on",
            }
        ),
    )

    validator = SkillValidator(
        policy=policy
    )

    promoter = SkillPromotionManager(
        library,
        validator=validator,
        policy=policy,
    )

    extractor = SkillExtractor()

    return ContinuousLearningScheduler(
        engine=engine,
        objectives=objectives,
        skill_library=library,
        skill_promotion_manager=promoter,
        skill_extractor=extractor,
    )
