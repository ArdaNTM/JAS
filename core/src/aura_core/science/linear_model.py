"""Bounded ordinary least squares over already supplied numerical observations.

Fitting is descriptive, local and deterministic. No causal, predictive
validity, safety, or statistical significance claim is implied.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .analysis import _checked_values


@dataclass(frozen=True, slots=True)
class LinearModel:
    slope: float
    intercept: float
    count: int
    r_squared: float | None
    residual_standard_error: float | None
    slope_standard_error: float | None = None
    intercept_standard_error: float | None = None

    def predict(self, x: int | float) -> float:
        if type(x) not in (int, float):
            raise ValueError("prediction input must be numeric")
        try:
            value = float(x)
        except (OverflowError, ValueError) as exc:
            raise ValueError("invalid prediction magnitude") from exc
        if not math.isfinite(value) or abs(value) > 1e100:
            raise ValueError("prediction input outside safe range")
        predicted = self.intercept + self.slope * value
        if not math.isfinite(predicted):
            raise ValueError("prediction overflow")
        return predicted

    def to_dict(self) -> dict[str, Any]:
        return {
            "slope": self.slope, "intercept": self.intercept,
            "count": self.count, "r_squared": self.r_squared,
            "residual_standard_error": self.residual_standard_error,
            "slope_standard_error": self.slope_standard_error,
            "intercept_standard_error": self.intercept_standard_error,
            "standard_error_assumptions": "independent, homoscedastic errors; NOT validated",
            "assumptions_verified": False,
            "inferential_claim": False, "untrusted_input": True,
        }


def fit_simple_linear_model(
    x: list[int | float] | tuple[int | float, ...],
    y: list[int | float] | tuple[int | float, ...],
) -> LinearModel:
    """Fit OLS intercept + slope to 2..10000 finite, paired observations."""
    xs, ys = _checked_values(x), _checked_values(y)
    if len(xs) != len(ys) or len(xs) < 2:
        raise ValueError("linear fitting requires >=2 paired observations")
    n = len(xs)
    mx, my = math.fsum(xs) / n, math.fsum(ys) / n
    dx = [item - mx for item in xs]
    dy = [item - my for item in ys]
    ssx = math.fsum(item * item for item in dx)
    if not math.isfinite(ssx) or ssx <= 0:
        raise ValueError("predictor variance must be positive and finite")
    slope = math.fsum(a * b for a, b in zip(dx, dy, strict=True)) / ssx
    intercept = my - slope * mx
    residuals = [
        yv - (intercept + slope * xv)
        for xv, yv in zip(xs, ys, strict=True)
    ]
    sse = math.fsum(value * value for value in residuals)
    sst = math.fsum(value * value for value in dy)
    if not all(math.isfinite(value) for value in (slope, intercept, sse, sst)):
        raise ValueError("non-finite regression result")
    r2 = None if sst == 0 else max(0.0, min(1.0, 1 - sse / sst))
    residual_se = math.sqrt(sse / (n - 2)) if n > 2 else None
    # Formal OLS uncertainty is conditional on unverified error assumptions.
    # Two-point fits have no residual degrees of freedom: no fake estimates.
    slope_se = intercept_se = None
    if residual_se is not None:
        root_ssx = math.sqrt(ssx)
        slope_se = residual_se / root_ssx
        intercept_se = residual_se * math.hypot(
            1 / math.sqrt(n), mx / root_ssx,
        )
        if not all(math.isfinite(z) for z in (slope_se, intercept_se)):
            raise ValueError("non-finite model uncertainty")
    return LinearModel(
        slope=slope, intercept=intercept, count=n, r_squared=r2,
        residual_standard_error=residual_se,
        slope_standard_error=slope_se, intercept_standard_error=intercept_se,
    )
