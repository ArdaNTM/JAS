"""Reproducible offline experiment analysis over bounded real CSV observations.

No model predictions, p-value claims, experimental ethics approval, or trusted
publisher identity are inferred from supplied data. Source bytes and method are
hashed so a separate reviewer can reproduce exact calculations.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

from aura_core.data_analysis.tabular import parse_csv_table
from aura_core.science.analysis import describe_sample, compare_independent_samples
from aura_core.science.model_uncertainty import fit_ols_with_uncertainty

_METHOD = "aura.exp.descriptive.v1"


@dataclass(frozen=True, slots=True)
class ExperimentReport:
    study_id: str
    data_sha256: str
    method: str
    sample_count: int
    result: dict[str, Any]
    report_sha256: str
    source_authenticated: bool = False
    methodology_approved: bool = False
    owner_accepted: bool = False
    untrusted: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "study_id": self.study_id,
            "data_sha256": self.data_sha256,
            "method": self.method,
            "sample_count": self.sample_count,
            "result": self.result,
            "report_sha256": self.report_sha256,
            "source_authenticated": False,
            "methodology_approved": False,
            "owner_accepted": False,
            "untrusted": True,
        }


def analyze_experiment_csv(
    csv_text: str, *, study_id: str, measure_column: str,
    group_column: str | None = None,
    x_column: str | None = None,
) -> ExperimentReport:
    """Analyze one numeric outcome, optionally split into 2 groups or fit OLS."""
    if (type(study_id) is not str or not 1 <= len(study_id) <= 100
        or not study_id.replace("-", "").replace("_", "").isalnum()):
        raise ValueError("invalid study_id")
    if type(csv_text) is not str:
        raise ValueError("CSV text must be string")
    table = parse_csv_table(csv_text)
    if measure_column not in table.columns:
        raise ValueError("measure column not found")
    if group_column is not None and group_column not in table.columns:
        raise ValueError("group column not found")
    if x_column is not None and x_column not in table.columns:
        raise ValueError("predictor column not found")
    if group_column is not None and x_column is not None:
        raise ValueError("choose group comparison or simple OLS, not both")
    if not table.rows:
        raise ValueError("experiment requires observations")

    y_index = table.columns.index(measure_column)
    try:
        values = [float(row[y_index]) for row in table.rows]
    except (ValueError, OverflowError) as exc:
        raise ValueError("measure column contains missing/nonnumeric observations") from exc
    if any(not math.isfinite(v) or abs(v) > 1e100 for v in values):
        raise ValueError("measure values must be finite and bounded")
    result: dict[str, Any] = {"summary": describe_sample(values).to_dict()}
    if group_column is not None:
        gi = table.columns.index(group_column)
        groups: dict[str, list[float]] = {}
        for row, val in zip(table.rows, values, strict=True):
            if not row[gi] or len(row[gi]) > 100:
                raise ValueError("group labels must be bounded")
            groups.setdefault(row[gi], []).append(val)
        if len(groups) != 2 or any(len(rows) < 2 for rows in groups.values()):
            raise ValueError("comparison requires exactly two groups of >=2 observations")
        keys = sorted(groups)
        result["groups"] = keys
        result["comparison"] = compare_independent_samples(groups[keys[0]], groups[keys[1]])
    if x_column is not None:
        xi = table.columns.index(x_column)
        try:
            xs = [float(row[xi]) for row in table.rows]
        except (ValueError, OverflowError) as exc:
            raise ValueError("predictor column contains missing/nonnumeric values") from exc
        result["linear_model"] = fit_ols_with_uncertainty(xs, values).to_dict()

    digest = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
    payload = json.dumps(
        {"study_id": study_id, "data_sha256": digest, "method": _METHOD,
         "result": result}, sort_keys=True, allow_nan=False, separators=(",", ":"))
    return ExperimentReport(
        study_id=study_id, data_sha256=digest, method=_METHOD,
        sample_count=len(values), result=result,
        report_sha256=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    )


def render_experiment_markdown(report: ExperimentReport) -> str:
    """Reviewable plain Markdown data, not an inference or ethics clearance."""
    if type(report) is not ExperimentReport:
        raise ValueError("ExperimentReport required")
    return (
        f"# AURA Experiment {report.study_id}\n\n"
        "Method: deterministic descriptive and OLS computations. "
        "Scientific assumptions and source authenticity are NOT independently validated.\n\n"
        f"Data SHA256: {report.data_sha256}\n\n"
        f"Count: {report.sample_count}\n\n"
        f"JSON results: " + json.dumps(report.result, sort_keys=True, allow_nan=False)
        + "\n"
    )
