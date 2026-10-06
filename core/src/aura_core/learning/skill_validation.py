from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Awaitable, Callable

from .skill_library import Skill, SkillLibrary


class SkillLifecycle(StrEnum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    PROMOTED = "promoted"
    QUARANTINED = "quarantined"


class ValidationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    severity: ValidationSeverity
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class SkillValidationResult:
    skill_id: str
    valid: bool
    score: float
    lifecycle: SkillLifecycle
    findings: tuple[ValidationFinding, ...]
    replay_attempted: bool
    replay_passed: bool

    @property
    def promotable(self) -> bool:
        return (
            self.valid
            and self.lifecycle
            is SkillLifecycle.VALIDATED
        )


@dataclass(frozen=True, slots=True)
class SkillPromotionPolicy:
    min_confidence: float = 0.80
    min_success_rate: float = 0.80
    min_success_count: int = 2
    min_validation_score: float = 0.85
    require_replay: bool = False
    disable_on_failure: bool = True


ReplayEvaluator = Callable[
    [Skill],
    Awaitable[bool],
]


class SkillValidator:
    """
    Validates a declarative skill before it can become persistent
    active capability.

    Validation is intentionally separate from execution. A skill never
    receives direct permission to invoke tools from this component.
    """

    def __init__(
        self,
        *,
        policy: SkillPromotionPolicy | None = None,
    ) -> None:
        self.policy = (
            policy
            or SkillPromotionPolicy()
        )

    def validate_structure(
        self,
        skill: Skill,
    ) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []

        if not skill.name.strip():
            findings.append(
                ValidationFinding(
                    ValidationSeverity.ERROR,
                    "EMPTY_NAME",
                    "Skill name is empty.",
                )
            )

        if not skill.description.strip():
            findings.append(
                ValidationFinding(
                    ValidationSeverity.ERROR,
                    "EMPTY_DESCRIPTION",
                    "Skill description is empty.",
                )
            )

        if not skill.steps:
            findings.append(
                ValidationFinding(
                    ValidationSeverity.ERROR,
                    "NO_STEPS",
                    "Skill contains no executable workflow steps.",
                )
            )

        if not skill.preconditions:
            findings.append(
                ValidationFinding(
                    ValidationSeverity.WARNING,
                    "NO_PRECONDITIONS",
                    "Skill has no explicit preconditions.",
                )
            )

        if not skill.postconditions:
            findings.append(
                ValidationFinding(
                    ValidationSeverity.WARNING,
                    "NO_POSTCONDITIONS",
                    "Skill has no explicit postconditions.",
                )
            )

        if not skill.source_run_ids:
            findings.append(
                ValidationFinding(
                    ValidationSeverity.ERROR,
                    "NO_PROVENANCE",
                    "Skill has no source learning run.",
                )
            )

        if not 0.0 <= skill.confidence <= 1.0:
            findings.append(
                ValidationFinding(
                    ValidationSeverity.ERROR,
                    "INVALID_CONFIDENCE",
                    "Skill confidence must be between 0 and 1.",
                )
            )

        if skill.success_count < 0:
            findings.append(
                ValidationFinding(
                    ValidationSeverity.ERROR,
                    "INVALID_SUCCESS_COUNT",
                    "Success count cannot be negative.",
                )
            )

        if skill.failure_count < 0:
            findings.append(
                ValidationFinding(
                    ValidationSeverity.ERROR,
                    "INVALID_FAILURE_COUNT",
                    "Failure count cannot be negative.",
                )
            )

        for index, step in enumerate(skill.steps):
            if not step.action.strip():
                findings.append(
                    ValidationFinding(
                        ValidationSeverity.ERROR,
                        "EMPTY_STEP_ACTION",
                        f"Step {index} has no action.",
                    )
                )

            if (
                step.capability_id is None
                and step.operation_id is None
            ):
                findings.append(
                    ValidationFinding(
                        ValidationSeverity.WARNING,
                        "UNBOUND_STEP",
                        (
                            f"Step {index} has no "
                            "capability/operation binding."
                        ),
                    )
                )

        return findings

    @staticmethod
    def _score(
        skill: Skill,
        findings: list[ValidationFinding],
        replay_passed: bool,
    ) -> float:
        score = 1.0

        for finding in findings:
            if finding.severity is ValidationSeverity.CRITICAL:
                score -= 0.50
            elif finding.severity is ValidationSeverity.ERROR:
                score -= 0.25
            elif finding.severity is ValidationSeverity.WARNING:
                score -= 0.05

        if skill.success_count > 0:
            score += min(
                0.10,
                skill.success_rate * 0.10,
            )

        if replay_passed:
            score += 0.10

        return max(
            0.0,
            min(1.0, score),
        )

    async def validate(
        self,
        skill: Skill,
        *,
        replay_evaluator: ReplayEvaluator | None = None,
    ) -> SkillValidationResult:
        findings = self.validate_structure(
            skill
        )

        replay_attempted = False
        replay_passed = False

        if (
            replay_evaluator is not None
            and not any(
                finding.severity
                in (
                    ValidationSeverity.ERROR,
                    ValidationSeverity.CRITICAL,
                )
                for finding in findings
            )
        ):
            replay_attempted = True

            try:
                replay_passed = bool(
                    await replay_evaluator(
                        skill
                    )
                )
            except Exception as exc:
                findings.append(
                    ValidationFinding(
                        ValidationSeverity.ERROR,
                        "REPLAY_ERROR",
                        (
                            "Replay validation raised "
                            f"{type(exc).__name__}: {exc}"
                        ),
                    )
                )

        if (
            self.policy.require_replay
            and not replay_passed
        ):
            findings.append(
                ValidationFinding(
                    ValidationSeverity.ERROR,
                    "REPLAY_REQUIRED",
                    "Promotion requires successful replay validation.",
                )
            )

        has_blocking = any(
            finding.severity
            in (
                ValidationSeverity.ERROR,
                ValidationSeverity.CRITICAL,
            )
            for finding in findings
        )

        score = self._score(
            skill,
            findings,
            replay_passed,
        )

        valid = (
            not has_blocking
            and score
            >= self.policy.min_validation_score
        )

        lifecycle = (
            SkillLifecycle.VALIDATED
            if valid
            else SkillLifecycle.QUARANTINED
        )

        return SkillValidationResult(
            skill_id=skill.skill_id,
            valid=valid,
            score=score,
            lifecycle=lifecycle,
            findings=tuple(findings),
            replay_attempted=replay_attempted,
            replay_passed=replay_passed,
        )


class SkillPromotionManager:
    """
    Controls the transition:

        candidate -> validated -> promoted
                              \
                               -> quarantined

    Promotion requires both structural validation and historical
    evidence. Merely generating or executing a skill once is never
    sufficient.
    """

    def __init__(
        self,
        library: SkillLibrary,
        *,
        validator: SkillValidator | None = None,
        policy: SkillPromotionPolicy | None = None,
    ) -> None:
        self.library = library

        self.policy = (
            policy
            or SkillPromotionPolicy()
        )

        self.validator = (
            validator
            or SkillValidator(
                policy=self.policy
            )
        )

    def _meets_promotion_gate(
        self,
        skill: Skill,
        validation: SkillValidationResult,
    ) -> bool:
        if not validation.promotable:
            return False

        if (
            validation.score
            < self.policy.min_validation_score
        ):
            return False

        if (
            skill.confidence
            < self.policy.min_confidence
        ):
            return False

        if (
            skill.success_rate
            < self.policy.min_success_rate
        ):
            return False

        if (
            skill.success_count
            < self.policy.min_success_count
        ):
            return False

        if (
            self.policy.require_replay
            and not validation.replay_passed
        ):
            return False

        return True

    async def evaluate(
        self,
        skill: Skill,
        *,
        replay_evaluator: ReplayEvaluator | None = None,
    ) -> SkillValidationResult:
        return await self.validator.validate(
            skill,
            replay_evaluator=replay_evaluator,
        )

    async def consider(
        self,
        skill: Skill,
        *,
        replay_evaluator: ReplayEvaluator | None = None,
    ) -> SkillValidationResult:
        validation = await self.evaluate(
            skill,
            replay_evaluator=replay_evaluator,
        )

        if self._meets_promotion_gate(
            skill,
            validation,
        ):
            skill.enabled = True

            await self.library.register(
                skill
            )

            return SkillValidationResult(
                skill_id=validation.skill_id,
                valid=validation.valid,
                score=validation.score,
                lifecycle=SkillLifecycle.PROMOTED,
                findings=validation.findings,
                replay_attempted=(
                    validation.replay_attempted
                ),
                replay_passed=(
                    validation.replay_passed
                ),
            )

        if self.policy.disable_on_failure:
            skill.enabled = False

        await self.library.register(
            skill
        )

        return SkillValidationResult(
            skill_id=validation.skill_id,
            valid=validation.valid,
            score=validation.score,
            lifecycle=(
                SkillLifecycle.QUARANTINED
                if not validation.valid
                else SkillLifecycle.VALIDATED
            ),
            findings=validation.findings,
            replay_attempted=(
                validation.replay_attempted
            ),
            replay_passed=(
                validation.replay_passed
            ),
        )

    async def consider_by_id(
        self,
        skill_id: str,
        *,
        replay_evaluator: ReplayEvaluator | None = None,
    ) -> SkillValidationResult | None:
        skill = await self.library.get(
            skill_id
        )

        if skill is None:
            return None

        return await self.consider(
            skill,
            replay_evaluator=replay_evaluator,
        )

    async def demote(
        self,
        skill_id: str,
    ) -> bool:
        skill = await self.library.get(
            skill_id
        )

        if skill is None:
            return False

        skill.enabled = False

        await self.library.register(
            skill
        )

        return True
