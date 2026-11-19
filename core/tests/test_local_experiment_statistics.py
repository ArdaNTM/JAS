"""Real descriptive computations and fail-closed local science inputs."""
from __future__ import annotations

import math

import pytest

from aura_core.science.analysis import (
    compare_independent_samples, describe_paired_changes, describe_sample,
)


def test_descriptive_sample_is_reproducible():
    a = describe_sample([1, 2, 3])
    assert a.count == 3
    assert a.mean == 2.0
    assert a.median == 2.0
    assert a.sample_variance == 1.0
    assert a.sample_standard_deviation == 1.0
    assert a.standard_error == pytest.approx(math.sqrt(1 / 3))
    assert a.sample_sha256 == describe_sample([1, 2, 3]).sample_sha256
    assert a.to_dict()["inferential_claim"] is False


def test_single_observation_does_not_invent_variance():
    a = describe_sample([7])
    assert a.mean == 7.0
    assert a.sample_variance is None
    assert a.standard_error is None


def test_independent_sample_difference_has_clear_direction():
    d = compare_independent_samples([1, 2, 3], [2, 3, 4])
    assert d["mean_difference"] == 1.0
    assert d["difference_standard_error"] == pytest.approx(math.sqrt(2 / 3))
    assert d["paired"] is False
    assert not d["inferential_claim"]


def test_paired_difference_uses_observation_order():
    d = describe_paired_changes([1, 2, 3], [2, 4, 6])
    assert d["paired"] is True
    assert d["changes"]["mean"] == 2.0
    assert d["changes"]["sample_variance"] == 1.0


@pytest.mark.parametrize("bad", [
    [], "123", [True], [float("nan")], [float("inf")],
    [1e120], [0, object()], [1] * 10001,
])
def test_invalid_samples_fail_closed(bad):
    with pytest.raises(ValueError):
        describe_sample(bad)


def test_paired_shape_mismatch_fails_closed():
    with pytest.raises(ValueError, match="equal lengths"):
        describe_paired_changes([1, 2], [1])


def test_large_constant_sample_is_stable_and_bounded():
    output = describe_sample([3] * 10000)
    assert output.mean == 3.0
    assert output.sample_variance == 0.0
    assert output.count == 10000
