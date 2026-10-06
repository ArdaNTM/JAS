from __future__ import annotations

from dataclasses import dataclass

from aura_core.kernel.permissions import RiskLevel


@dataclass(frozen=True, slots=True)
class GeneratedStep:
    step_id: str
    capability_id: str
    operation_id: str
    tool_name: str
    risk_level: RiskLevel
    arguments: dict[str, object]
    depends_on: set[str]
    max_attempts: int = 1


@dataclass(frozen=True, slots=True)
class GeneratedPlan:
    resource_scope: str
    steps: tuple[GeneratedStep, ...]


class DirectivePlanner:
    """
    Deterministic, allow-listed directive planner.

    Natural language is never converted into arbitrary tool calls.
    Only known capabilities are emitted.
    """

    _RESEARCH_TERMS = (
        "araştır",
        "araştırma",
        "research",
        "search",
        "bul",
        "incele",
        "öğren",
        "bilgi",
        "hakkında",
    )

    def plan(self, directive: str) -> GeneratedPlan:
        text = directive.strip()

        if not text:
            raise ValueError("Directive is required.")

        normalized = text.casefold()

        if any(term in normalized for term in self._RESEARCH_TERMS):
            return GeneratedPlan(
                resource_scope="public-web",
                steps=(
                    GeneratedStep(
                        step_id="research-search",
                        capability_id="internet.search",
                        operation_id="internet.search",
                        tool_name="search",
                        risk_level=RiskLevel.LOW,
                        arguments={"query": text},
                        depends_on=set(),
                        max_attempts=1,
                    ),
                ),
            )

        raise ValueError(
            "No governed capability matches this directive. "
            "Supported autonomous directive: research/search."
        )