from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from aura_core.models.multi_router import LLMProvider


class CriticSeverity(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class CriticFinding:
    category: str
    severity: CriticSeverity
    description: str
    evidence: str
    recommendation: str


@dataclass(frozen=True, slots=True)
class CriticResult:
    passed: bool
    score: float
    findings: tuple[CriticFinding, ...]
    strengths: tuple[str, ...]
    missing: tuple[str, ...]
    summary: str

    @property
    def needs_refinement(self) -> bool:
        return (
            not self.passed
            or bool(self.findings)
            or bool(self.missing)
        )


class LearningCritic:
    """
    Deterministic interface around an LLM critic.

    The critic never mutates knowledge or memory. It only produces
    structured findings which a separate refiner may consume.
    """

    def __init__(
        self,
        *,
        llm: LLMProvider,
        max_findings: int = 8,
    ) -> None:
        if max_findings < 1:
            raise ValueError(
                "max_findings must be positive"
            )

        self.llm = llm
        self.max_findings = max_findings

    def _prompt(
        self,
        *,
        objective: str,
        output: str,
        context: str = "",
    ) -> str:
        return f"""
You are AURA's independent critic.

Audit the supplied learning objective and output.

Check:
1. factual support
2. logical consistency
3. missing information
4. unsupported assumptions
5. contradictions
6. actionability
7. unnecessary repetition
8. whether the output actually addresses the objective

Do not invent evidence.
Do not rewrite the output.
Only identify problems and strengths.

Return ONLY valid JSON:
{{
  "passed": true,
  "score": 0.0,
  "summary": "string",
  "strengths": ["string"],
  "missing": ["string"],
  "findings": [
    {{
      "category": "factual|logic|completeness|assumption|contradiction|relevance|quality",
      "severity": "none|low|medium|high|critical",
      "description": "string",
      "evidence": "string",
      "recommendation": "string"
    }}
  ]
}}

OBJECTIVE:
{objective}

OUTPUT:
{output}

ADDITIONAL CONTEXT:
{context or "none"}
""".strip()

    async def critique(
        self,
        *,
        objective: str,
        output: str,
        context: str = "",
    ) -> CriticResult:
        raw = await self.llm.generate(
            self._prompt(
                objective=objective,
                output=output,
                context=context,
            ),
            options={
                "temperature": 0,
                "format": "json",
            },
        )

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Critic returned invalid JSON"
            ) from exc

        if not isinstance(payload, dict):
            raise RuntimeError(
                "Critic returned a non-object"
            )

        try:
            score = float(
                payload.get("score", 0.0)
            )
        except (TypeError, ValueError):
            score = 0.0

        score = max(
            0.0,
            min(1.0, score),
        )

        passed = bool(
            payload.get("passed", False)
        )

        strengths = tuple(
            str(item).strip()
            for item in (
                payload.get("strengths", [])
                if isinstance(
                    payload.get("strengths", []),
                    list,
                )
                else []
            )
            if str(item).strip()
        )[: self.max_findings]

        missing = tuple(
            str(item).strip()
            for item in (
                payload.get("missing", [])
                if isinstance(
                    payload.get("missing", []),
                    list,
                )
                else []
            )
            if str(item).strip()
        )[: self.max_findings]

        findings: list[CriticFinding] = []

        raw_findings = payload.get(
            "findings",
            [],
        )

        if isinstance(raw_findings, list):
            for item in raw_findings[
                : self.max_findings
            ]:
                if not isinstance(item, dict):
                    continue

                try:
                    severity = CriticSeverity(
                        str(
                            item.get(
                                "severity",
                                "medium",
                            )
                        ).lower()
                    )
                except ValueError:
                    severity = CriticSeverity.MEDIUM

                findings.append(
                    CriticFinding(
                        category=str(
                            item.get(
                                "category",
                                "quality",
                            )
                        ),
                        severity=severity,
                        description=str(
                            item.get(
                                "description",
                                "",
                            )
                        ).strip(),
                        evidence=str(
                            item.get(
                                "evidence",
                                "",
                            )
                        ).strip(),
                        recommendation=str(
                            item.get(
                                "recommendation",
                                "",
                            )
                        ).strip(),
                    )
                )

        return CriticResult(
            passed=passed,
            score=score,
            findings=tuple(findings),
            strengths=strengths,
            missing=missing,
            summary=str(
                payload.get(
                    "summary",
                    "",
                )
            ).strip(),
        )
