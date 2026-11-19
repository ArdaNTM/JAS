"""Finite-sample OLS parameter uncertainty with explicit statistical assumptions.

This module does not claim verified causality, independent sample provenance or
validity of iid, Gaussian and homoscedastic residual assumptions. The 95% CI
uses a large-sample normal approximation only for n>=30; callers must validate
assumptions and scientific methodology independently.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from typing import Any

from aura_core.science.analysis import _checked_values
from aura_core.science.linear_model import fit_simple_linear_model


@dataclass(frozen=True, slots=True)
class OLSUncertainty:
    slope: float
    intercept: float
    slope_standard_error: float
    intercept_standard_error: float
    residual_standard_error: float
    r_squared: float | None
    degrees_freedom: int
    slope_interval_95_approx: tuple[float, float] | None
    intercept_interval_95_approx: tuple[float, float] | None
    paired_data_sha256: str
    assumptions_verified: bool = False
    source_authenticity_verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "slope": self.slope,
            "intercept": self.intercept,
            "slope_standard_error": self.slope_standard_error,
            "intercept_standard_error": self.intercept_standard_error,
            "residual_standard_error": self.residual_standard_error,
            "r_squared": self.r_squared,
            "degrees_freedom": self.degrees_freedom,
            "slope_interval_95_normal_approx": self.slope_interval_95_approx,
            "intercept_interval_95_normal_approx": self.intercept_interval_95_approx,
            "paired_data_sha256": self.paired_data_sha256,
            "assumptions_verified": False,
            "source_authenticity_verified": False,
            "untrusted_input": True,
            "causal_claim": False,
        }


def fit_ols_with_uncertainty(
    x: list[int | float] | tuple[int | float, ...],
    y: list[int | float] | tuple[int | float, ...],
) -> OLSUncertainty:
    xs, ys = _checked_values(x), _checked_values(y)
    if len(xs) != len(ys) or not 3 <= len(xs) <= 10_000:
        raise ValueError("OLS uncertainty requires 3..10000 paired observations")
    model = fit_simple_linear_model(xs, ys)
    n = len(xs)
    mean_x = math.fsum(xs) / n
    ssx = math.fsum((v - mean_x) ** 2 for v in xs)
    if ssx <= 0 or not math.isfinite(ssx):
        raise ValueError("finite predictor variance required")
    residual_se = model.residual_standard_error
    if residual_se is None or not math.isfinite(residual_se):
        raise ValueError("residual error is not finite")
    slope_se = residual_se / math.sqrt(ssx)
    intercept_se = residual_se * math.sqrt(1 / n + (mean_x ** 2) / ssx)
    if not all(math.isfinite(t) for t in (slope_se, intercept_se)):
        raise ValueError("non-finite parameter standard errors")
    # Asymptotic normal CI is reported only when n>=30. Not a Student-t CI.
    z = statistics.NormalDist().inv_cdf(0.975)
    slope_interval = (
        (model.slope - z * slope_se, model.slope + z * slope_se)
        if n >= 30 else None
    )
    intercept_interval = (
        (model.intercept - z * intercept_se, model.intercept + z * intercept_se)
        if n >= 30 else None
    )
    digest = hashlib.sha256(json.dumps(
        {"x": xs, "y": ys}, allow_nan=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()
    return OLSUncertainty(
        slope=model.slope, intercept=model.intercept,
        slope_standard_error=slope_se,
        intercept_standard_error=intercept_se,
        residual_standard_error=residual_se, r_squared=model.r_squared,
        degrees_freedom=n - 2,
        slope_interval_95_approx=slope_interval,
        intercept_interval_95_approx=intercept_interval,
        paired_data_sha256=digest,
    )
