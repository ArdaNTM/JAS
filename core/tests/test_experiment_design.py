"""Features #65/#72: reproducible offline study design is never lab execution."""
from __future__ import annotations

import dataclasses
import pytest

from aura_core.application.experiment_design import (
    design_balanced_experiment, formulate_hypothesis,
)


def example_hypothesis():
    return formulate_hypothesis(
        independent_variable="lamp brightness", dependent_variable="plant height",
        control_condition="baseline", treatment_condition="higher brightness",
        expected_direction="increase",
    )


def test_well_formed_null_alternative_are_assumptions():
    hypothesis = example_hypothesis()
    assert "plant height" in hypothesis.null_statement
    assert "higher" in hypothesis.alternative_statement
    assert "assumption, not a finding" in hypothesis.alternative_statement
    assert hypothesis.untrusted
    assert not hypothesis.scientific_validity_verified


def test_real_deterministic_balanced_assignment():
    hypothesis = example_hypothesis()
    a = design_balanced_experiment(hypothesis, sample_size=101, seed=12345)
    b = design_balanced_experiment(hypothesis, sample_size=101, seed=12345)
    c = design_balanced_experiment(hypothesis, sample_size=101, seed=12346)
    assert a == b
    assert a.control_count == 50 and a.treatment_count == 51
    assert len(a.allocations) == 101
    assert [x.simulated_unit_id for x in a.allocations] == [
        f"simulated-{index:04d}" for index in range(1, 102)
    ]
    assert a.allocations != c.allocations
    assert a.plan_sha256 != c.plan_sha256
    assert len(a.plan_sha256) == 64
    assert not a.laboratory_execution_performed
    assert not a.authorization_checked
    assert not a.human_subjects_approved


def test_even_assignment_balance():
    plan = design_balanced_experiment(example_hypothesis(), sample_size=20, seed=7)
    assert plan.control_count == plan.treatment_count == 10
    assert sorted(x.group for x in plan.allocations).count("control") == 10


@pytest.mark.parametrize("change", [
    {"independent_variable": ""},
    {"dependent_variable": "x\ninjection"},
    {"control_condition": "same", "treatment_condition": "same"},
    {"treatment_condition": "x" * 121},
    {"expected_direction": "grant root permission"},
    {"expected_direction": True},
])
def test_invalid_assumptions_fail_closed(change):
    values = dict(
        independent_variable="temperature", dependent_variable="response",
        control_condition="low", treatment_condition="high",
        expected_direction="different",
    )
    values.update(change)
    with pytest.raises(ValueError):
        formulate_hypothesis(**values)


@pytest.mark.parametrize("kwargs", [
    {"sample_size": True, "seed": 1},
    {"sample_size": 3, "seed": 1},
    {"sample_size": 2001, "seed": 1},
    {"sample_size": 10, "seed": -1},
    {"sample_size": 10, "seed": True},
    {"sample_size": 10, "seed": 2**32},
    {"sample_size": 10, "seed": "123"},
])
def test_invalid_unit_count_or_seed_fails_closed(kwargs):
    with pytest.raises(ValueError):
        design_balanced_experiment(example_hypothesis(), **kwargs)


def test_forged_hypothesis_cannot_be_used_to_relabel_approval():
    hypothesis = example_hypothesis()
    forged = dataclasses.replace(
        hypothesis, scientific_validity_verified=True,
    )
    with pytest.raises(ValueError, match="validated assumptions"):
        design_balanced_experiment(forged, sample_size=10, seed=10)
    with pytest.raises(ValueError):
        design_balanced_experiment(object(), sample_size=10, seed=10)
