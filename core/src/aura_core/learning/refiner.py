from __future__ import annotations

import json
from dataclasses import dataclass

from aura_core.learning.critic import CriticResult
from aura_core.learning.models import LearningObjective
from aura_core.models.multi_router import LLMProvider


@dataclass(frozen=True, slots=True)
class RefinementResult:
    objective: LearningObjective
    changed: bool
    rationale: str
    constraints: tuple[str, ...]


class LearningRefiner:
    """
    Converts critic findings into a safer, narrower learning objective.

    The refiner does not directly modify knowledge, memory, permissions,
    tools, providers, or the kernel.
    """

    def __init__(
        self,
        *,
        llm: LLMProvider,
        max_constraints: int = 8,
    ) -> None:
        self.llm = llm
        self.max_constraints = max_constraints

    async def refine(
        self,
        objective: LearningObjective,
        critique: CriticResult,
    ) -> RefinementResult:
        if not critique.needs_refinement:
            return RefinementResult(
                objective=objective,
                changed=False,
                rationale="Critic found no refinement requirement.",
                constraints=(),
            )

        findings = "\n".join(
            (
                f"- [{finding.severity.value}] "
                f"{finding.category}: "
                f"{finding.description} "
                f"Recommendation: "
                f"{finding.recommendation}"
            )
            for finding in critique.findings
        )

        missing = "\n".join(
            f"- {item}"
            for item in critique.missing
        )

        prompt = f"""
You are AURA's objective refiner.

Refine the learning objective using ONLY the critic findings.

Preserve the original intent.
Do not broaden the objective.
Do not invent requirements.
Make the objective more precise, testable, evidence-oriented,
and resistant to unsupported conclusions.

Return ONLY valid JSON:
{{
  "title": "string",
  "description": "string",
  "changed": true,
  "rationale": "string",
  "constraints": ["string"]
}}

ORIGINAL TITLE:
{objective.title or ""}

ORIGINAL OBJECTIVE:
{objective.description}

CRITIC SCORE:
{critique.score}

CRITIC SUMMARY:
{critique.summary}

FINDINGS:
{findings or "none"}

MISSING:
{missing or "none"}
""".strip()

        raw = await self.llm.generate(
            prompt,
            options={
                "temperature": 0,
                "format": "json",
            },
        )

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Refiner returned invalid JSON"
            ) from exc

        if not isinstance(payload, dict):
            raise RuntimeError(
                "Refiner returned a non-object"
            )

        title = str(
            payload.get(
                "title",
                objective.title or "",
            )
        ).strip()

        description = str(
            payload.get(
                "description",
                objective.description,
            )
        ).strip()

        if not description:
            description = objective.description

        constraints = tuple(
            str(item).strip()
            for item in (
                payload.get(
                    "constraints",
                    [],
                )
                if isinstance(
                    payload.get(
                        "constraints",
                        [],
                    ),
                    list,
                )
                else []
            )
            if str(item).strip()
        )[: self.max_constraints]

        changed = bool(
            payload.get(
                "changed",
                (
                    description
                    != objective.description
                    or title
                    != (objective.title or "")
                ),
            )
        )

        refined = LearningObjective(
            objective_id=objective.objective_id,
            title=title or None,
            description=description,
            priority=objective.priority,
            enabled=objective.enabled,
        )

        return RefinementResult(
            objective=refined,
            changed=changed,
            rationale=str(
                payload.get(
                    "rationale",
                    "",
                )
            ).strip(),
            constraints=constraints,
        )
