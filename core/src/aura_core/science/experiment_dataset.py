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
from aura_core.application.experiment_design import ExperimentDesign, design_balanced_experiment

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



@dataclass(frozen=True, slots=True)
class DesignLinkedExperiment:
    """Report with reproducible simulated-assignment checks, not a validity seal."""

    report: ExperimentReport
    design_sha256: str
    linkage_sha256: str
    design_record_consistent: bool = True
    independent_scientific_review: bool = False
    human_subject_consent_verified: bool = False
    actual_randomization_verified: bool = False
    source_authenticated: bool = False


def analyze_experiment_with_design(
    csv_text: str, *, plan: ExperimentDesign, study_id: str,
    measure_column: str = "measure", group_column: str = "group",
    unit_column: str = "unit_id",
) -> DesignLinkedExperiment:
    """Validate exact row-to-planned simulated unit mapping before analysis.

    This checks a caller-provided CSV against a deterministic offline *plan*.
    It does NOT prove a real-world randomization or experimental legitimacy.
    """
    if type(plan) is not ExperimentDesign:
        raise ValueError("validated experiment plan required")
    validated = design_balanced_experiment(
        plan.hypothesis, sample_size=plan.sample_size, seed=plan.seed)
    if plan != validated:
        raise ValueError("tampered or non-canonical experiment design")
    if type(csv_text) is not str:
        raise ValueError("CSV source must be string")
    table = parse_csv_table(csv_text)
    if not all(type(col) is str and col in table.columns
               for col in (measure_column, group_column, unit_column)):
        raise ValueError("unit/group/measure columns required")
    if len(set((measure_column, group_column, unit_column))) != 3:
        raise ValueError("experiment columns must be distinct")
    if len(table.rows) != plan.sample_size:
        raise ValueError("observation count differs from recorded study plan")
    unit_index, group_index = (
        table.columns.index(unit_column), table.columns.index(group_column))
    recorded = {}
    for row in table.rows:
        unit, group = row[unit_index], row[group_index]
        if not unit or unit in recorded:
            raise ValueError("duplicate or missing experiment unit identity")
        recorded[unit] = group
    intended = {item.simulated_unit_id: item.group for item in plan.allocations}
    if recorded != intended:
        raise ValueError("experiment allocation does not match recorded design")
    report = analyze_experiment_csv(
        csv_text, study_id=study_id, measure_column=measure_column,
        group_column=group_column)
    if report.sample_count != plan.sample_size:
        raise ValueError("experiment sample count mismatch")
    material = json.dumps(
        {"report": report.report_sha256, "plan": plan.plan_sha256,
         "study_id": study_id},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return DesignLinkedExperiment(
        report=report, design_sha256=plan.plan_sha256,
        linkage_sha256=hashlib.sha256(material).hexdigest())


async def analyze_governed_experiment(
    *, gateway: object, request: object, principal_id: str,
    plan: ExperimentDesign, study_id: str,
) -> DesignLinkedExperiment:
    """Read structured CSV through an actual authorized MCP Gateway dispatch.

    The provider response is untrusted sample data. The caller supplies the
    pre-reviewed plan; this method confers NO scientific or consent approval.
    """
    from aura_core.kernel.permissions import AuthorizationDecision
    from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
    if (not isinstance(gateway, MCPGateway) or
        not isinstance(request, MCPGatewayRequest) or
        type(principal_id) is not str or request.principal_id != principal_id):
        raise PermissionError("authenticated principal and real MCP Gateway required")
    result = await gateway.invoke(request)
    if result.decision is not AuthorizationDecision.ALLOW:
        raise PermissionError("experiment dataset retrieval denied by MCP Gateway")
    data = result.result
    if not isinstance(data, dict):
        data = getattr(data, "structured_content", None) or getattr(
            data, "structuredContent", None)
    if type(data) is not dict or set(data) != {"csv_text"}:
        raise ValueError("experiment source must be structured CSV content")
    return analyze_experiment_with_design(
        data["csv_text"], plan=plan, study_id=study_id)



def render_design_linked_experiment_markdown(linked: DesignLinkedExperiment) -> str:
    """Reproducible report of measured data and recorded plan; no approval claim."""
    if type(linked) is not DesignLinkedExperiment:
        raise ValueError("verified report wrapper required")
    return (
        render_experiment_markdown(linked.report)
        + "\nRecorded experiment plan SHA256: " + linked.design_sha256
        + "\nLinkage SHA256: " + linked.linkage_sha256
        + "\nDesign-to-observation labels checked: "
        + ("yes" if linked.design_record_consistent else "no")
        + "\nIndependent scientific review, actual randomization and "
          "participant consent: NOT VERIFIED.\n"
    )
