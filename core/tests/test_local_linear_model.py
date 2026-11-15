"""Ordinary least squares is deterministic and rejects invalid experiments."""
from __future__ import annotations

import pytest

from aura_core.science.linear_model import fit_simple_linear_model


def test_exact_line_has_expected_coefficients_and_r2():
    model = fit_simple_linear_model([0, 1, 2, 3], [1, 3, 5, 7])
    assert model.slope == pytest.approx(2.0)
    assert model.intercept == pytest.approx(1.0)
    assert model.r_squared == pytest.approx(1.0)
    assert model.residual_standard_error == pytest.approx(0.0)
    assert model.predict(5) == pytest.approx(11.0)
    assert model.to_dict()["inferential_claim"] is False


def test_constant_target_does_not_invent_r_squared():
    model = fit_simple_linear_model([1, 2, 3], [4, 4, 4])
    assert model.slope == 0.0
    assert model.intercept == 4.0
    assert model.r_squared is None


@pytest.mark.parametrize("x,y", [
    ([1], [2]), ([1, 2], [1]), ([1, 1], [2, 3]),
    ([1, True], [2, 3]), ([1, float("nan")], [2, 3]),
    ([1e150, 2e150], [2, 3]),
])
def test_unfit_data_rejected(x, y):
    with pytest.raises(ValueError):
        fit_simple_linear_model(x, y)


@pytest.mark.parametrize("value", [True, "2", float("nan"), float("inf"), 1e150])
def test_predict_rejects_unsafe_values(value):
    model = fit_simple_linear_model([1, 2, 3], [2, 4, 6])
    with pytest.raises(ValueError):
        model.predict(value)


def test_predictions_are_only_descriptive_model_outputs():
    model = fit_simple_linear_model([1, 2, 3, 4], [1, 0, 3, 1])
    assert model.r_squared is not None
    assert 0 <= model.r_squared <= 1
    assert model.count == 4
    assert model.to_dict()["untrusted_input"] is True
