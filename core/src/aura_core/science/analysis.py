"""Deterministic descriptive statistics for bounded local experimental results.

This library computes *descriptive* observations. No p-value, causal claim,
forecast, inference provider, device control, or tool authorization is implied.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from typing import Any


_MAX_VALUES = 10_000
_MAX_MAGNITUDE = 1e100


def _checked_values(values: list[int | float] | tuple[int | float, ...]) -> tuple[float, ...]:
    if not isinstance(values, (tuple, list)) or not 1 <= len(values) <= _MAX_VALUES:
        raise ValueError("sample must contain 1..10000 numbers")
    output: list[float] = []
    for item in values:
        if type(item) not in (int, float):
            raise ValueError("sample values must be numbers, not booleans")
        try:
            number = float(item)
        except (OverflowError, ValueError) as exc:
            raise ValueError("sample magnitude is unsupported") from exc
        if not math.isfinite(number) or abs(number) > _MAX_MAGNITUDE:
            raise ValueError("sample values must be finite and bounded")
        output.append(number)
    return tuple(output)


@dataclass(frozen=True, slots=True)
class SampleSummary:
    count: int
    mean: float
    median: float
    minimum: float
    maximum: float
    sample_variance: float | None
    sample_standard_deviation: float | None
    standard_error: float | None
    sample_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count, "mean": self.mean, "median": self.median,
            "minimum": self.minimum, "maximum": self.maximum,
            "sample_variance": self.sample_variance,
            "sample_standard_deviation": self.sample_standard_deviation,
            "standard_error": self.standard_error,
            "sample_sha256": self.sample_sha256,
            "untrusted_input": True, "inferential_claim": False,
        }


def describe_sample(values: list[int | float] | tuple[int | float, ...]) -> SampleSummary:
    """Compute reproducible bounded descriptive statistics."""
    sample = _checked_values(values)
    count = len(sample)
    mean = math.fsum(sample) / count
    median = float(statistics.median(sample))
    variance = (
        math.fsum((number - mean) ** 2 for number in sample) / (count - 1)
        if count > 1 else None
    )
    if variance is not None and not math.isfinite(variance):
        raise ValueError("sample variance overflow")
    deviation = math.sqrt(variance) if variance is not None else None
    stderr = deviation / math.sqrt(count) if deviation is not None else None
    digest = hashlib.sha256(
        json.dumps(sample, allow_nan=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return SampleSummary(
        count=count, mean=mean, median=median, minimum=min(sample),
        maximum=max(sample), sample_variance=variance,
        sample_standard_deviation=deviation, standard_error=stderr,
        sample_sha256=digest,
    )


def compare_independent_samples(
    reference: list[int | float] | tuple[int | float, ...],
    observed: list[int | float] | tuple[int | float, ...],
) -> dict[str, Any]:
    """Return descriptive effect and SEM; not a statistical significance test."""
    left = describe_sample(reference)
    right = describe_sample(observed)
    standard_error = (
        math.sqrt(
            left.sample_variance / left.count
            + right.sample_variance / right.count
        )
        if left.sample_variance is not None
        and right.sample_variance is not None else None
    )
    return {
        "reference": left.to_dict(), "observed": right.to_dict(),
        "mean_difference": right.mean - left.mean,
        "difference_standard_error": standard_error,
        "paired": False, "inferential_claim": False,
    }


def describe_paired_changes(
    before: list[int | float] | tuple[int | float, ...],
    after: list[int | float] | tuple[int | float, ...],
) -> dict[str, Any]:
    """Describe paired changes; caller supplies matching observation order."""
    a = _checked_values(before)
    b = _checked_values(after)
    if len(a) != len(b):
        raise ValueError("paired samples must have equal lengths")
    changes = [end - start for start, end in zip(a, b, strict=True)]
    if any(not math.isfinite(item) for item in changes):
        raise ValueError("paired difference overflow")
    return {
        "changes": describe_sample(changes).to_dict(),
        "paired": True, "inferential_claim": False,
    }
