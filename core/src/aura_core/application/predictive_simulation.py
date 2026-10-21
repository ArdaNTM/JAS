"""Deterministic, conservative pre-execution simulation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class SimulationFinding:
    code: str
    severity: str
    message: str
    step_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "step_id": self.step_id,
        }


class PredictiveSimulator:
    """Static analysis of declared plans; does not call tools or claim certainty."""

    def simulate(self, steps: Iterable[Any]) -> dict[str, Any]:
        items = tuple(steps)
        findings: list[SimulationFinding] = []
        ids = [str(getattr(step, "step_id", "")) for step in items]
        if len(ids) != len(set(ids)):
            findings.append(SimulationFinding("duplicate_step_id", "block", "Plan contains duplicate step identifiers."))
        known = set(ids)
        side_effecting = 0
        high_risk = 0
        for step in items:
            step_id = str(getattr(step, "step_id", "")) or None
            risk = getattr(getattr(step, "risk_level", None), "value", str(getattr(step, "risk_level", ""))).casefold()
            args = getattr(step, "arguments", {}) or {}
            deps = set(getattr(step, "depends_on", ()) or ())
            missing = sorted(deps - known)
            if missing:
                findings.append(SimulationFinding("missing_dependency", "block", f"Dependencies are missing: {', '.join(missing)}.", step_id))
            if risk in {"high", "critical", "dangerous"}:
                high_risk += 1
                findings.append(SimulationFinding("high_risk_operation", "review", "High-risk operation needs explicit review and authorization.", step_id))
            if risk in {"medium", "high", "critical", "dangerous"}:
                side_effecting += 1
                findings.append(SimulationFinding("possible_side_effect", "review", "The declared risk level suggests possible side effects; this simulation cannot verify tool behavior.", step_id))
            if len(repr(args)) > 12000:
                findings.append(SimulationFinding("large_arguments", "review", "Arguments are unusually large; inspect data exposure and tool limits.", step_id))
        if len(items) > 16:
            findings.append(SimulationFinding("large_plan", "review", "Plan is large; consider splitting it into bounded stages."))
        blockers = sum(item.severity == "block" for item in findings)
        reviews = sum(item.severity == "review" for item in findings)
        return {
            "simulator_version": "1.0",
            "steps_analyzed": len(items),
            "predicted_side_effecting_steps": side_effecting,
            "high_risk_steps": high_risk,
            "blockers": blockers,
            "reviews_required": reviews,
            "recommendation": "do_not_execute" if blockers else "review_before_execution" if reviews else "ready_for_authorization_check",
            "findings": [item.to_dict() for item in findings],
            "limitations": "Static heuristic only; does not execute tools, infer undocumented effects, or replace PermissionEngine/MCPGateway authorization.",
        }
