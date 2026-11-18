"""Offline, non-executing experimental hypotheses and balanced trial assignment.

Plans are *simulated* study templates, not scientific validation, IRB/ethics
approval, participant enrollment, hardware actuation, or MCP authorization.
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass

_DIRECTIONS = {"increase", "decrease", "different"}


@dataclass(frozen=True, slots=True)
class StudyHypothesis:
    independent_variable: str
    dependent_variable: str
    control_condition: str
    treatment_condition: str
    expected_direction: str
    null_statement: str
    alternative_statement: str
    untrusted: bool = True
    scientific_validity_verified: bool = False


@dataclass(frozen=True, slots=True)
class TrialAllocation:
    simulated_unit_id: str
    group: str


@dataclass(frozen=True, slots=True)
class ExperimentDesign:
    hypothesis: StudyHypothesis
    sample_size: int
    seed: int
    control_count: int
    treatment_count: int
    allocations: tuple[TrialAllocation, ...]
    plan_sha256: str
    laboratory_execution_performed: bool = False
    human_subjects_approved: bool = False
    scientific_validity_verified: bool = False
    authorization_checked: bool = False


def _label(value: str) -> str:
    if (
        type(value) is not str or not 1 <= len(value.strip()) <= 120
        or value != value.strip()
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
    ):
        raise ValueError("bounded, single-line study label required")
    return value


def formulate_hypothesis(
    *, independent_variable: str, dependent_variable: str,
    control_condition: str, treatment_condition: str,
    expected_direction: str,
) -> StudyHypothesis:
    """Create explicit H0/H1 wording from user-supplied assumptions only."""
    independent = _label(independent_variable)
    dependent = _label(dependent_variable)
    control = _label(control_condition)
    treatment = _label(treatment_condition)
    if control.casefold() == treatment.casefold():
        raise ValueError("control and treatment must differ")
    if type(expected_direction) is not str or expected_direction not in _DIRECTIONS:
        raise ValueError("expected direction must be increase/decrease/different")
    hypothesis_0 = (
        f"Null: the measured {dependent} does not differ between "
        f"{control} and {treatment}."
    )
    interpretation = {
        "increase": "higher",
        "decrease": "lower",
        "different": "different",
    }[expected_direction]
    hypothesis_1 = (
        f"Alternative (assumption, not a finding): changing {independent} "
        f"from {control} to {treatment} yields {interpretation} measured "
        f"{dependent}."
    )
    return StudyHypothesis(
        independent, dependent, control, treatment, expected_direction,
        hypothesis_0, hypothesis_1,
    )


def design_balanced_experiment(
    hypothesis: StudyHypothesis, *, sample_size: int, seed: int,
) -> ExperimentDesign:
    """Assign purely simulated trial labels deterministically, without IO."""
    if type(hypothesis) is not StudyHypothesis:
        raise ValueError("StudyHypothesis required")
    expected = formulate_hypothesis(
        independent_variable=hypothesis.independent_variable,
        dependent_variable=hypothesis.dependent_variable,
        control_condition=hypothesis.control_condition,
        treatment_condition=hypothesis.treatment_condition,
        expected_direction=hypothesis.expected_direction,
    )
    if hypothesis != expected:
        raise ValueError("hypothesis text must match validated assumptions")
    if type(sample_size) is not int or not 4 <= sample_size <= 2000:
        raise ValueError("sample_size must be 4..2000")
    if type(seed) is not int or not 0 <= seed <= 0xFFFFFFFF:
        raise ValueError("seed must be an unsigned 32-bit integer")
    control_count = sample_size // 2
    treatment_count = sample_size - control_count
    conditions = ["control"] * control_count + ["treatment"] * treatment_count
    # Standard PRNG: reproducible allocation, NOT cryptographic or suitable
    # for blind human-subject enrollment without independent study review.
    random.Random(seed).shuffle(conditions)
    allocations = tuple(
        TrialAllocation(f"simulated-{index:04d}", group)
        for index, group in enumerate(conditions, start=1)
    )
    canonical = json.dumps(
        {
            "independent": hypothesis.independent_variable,
            "dependent": hypothesis.dependent_variable,
            "control": hypothesis.control_condition,
            "treatment": hypothesis.treatment_condition,
            "direction": hypothesis.expected_direction,
            "sample_size": sample_size,
            "seed": seed,
            "groups": conditions,
        },
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return ExperimentDesign(
        hypothesis=hypothesis,
        sample_size=sample_size,
        seed=seed,
        control_count=control_count,
        treatment_count=treatment_count,
        allocations=allocations,
        plan_sha256=digest,
    )
