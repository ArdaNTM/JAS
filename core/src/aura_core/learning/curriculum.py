from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from aura_core.learning.models import LearningObjective
from aura_core.models.multi_router import LLMProvider


@dataclass(frozen=True, slots=True)
class CuriosityCandidate:
    objective_id: str
    title: str
    description: str
    priority: int
    rationale: str
    novelty: float
    information_gain: float
    difficulty: float


class CuriosityEngine:
    """
    Generates bounded learning objectives from:
      - existing objectives
      - knowledge gaps
      - previous reflections
      - failed learning episodes
      - unexplored directions

    It proposes objectives only. It never executes tools or bypasses
    the PermissionEngine.
    """

    def __init__(
        self,
        *,
        llm: LLMProvider | None = None,
        max_candidates: int = 5,
    ) -> None:
        if max_candidates < 1:
            raise ValueError(
                "max_candidates must be positive"
            )

        self.llm = llm
        self.max_candidates = max_candidates

    @staticmethod
    def _objective_id(
        title: str,
        description: str,
    ) -> str:
        return str(
            uuid5(
                NAMESPACE_URL,
                (
                    "aura-curiosity:"
                    f"{title.strip()}:{description.strip()}"
                ),
            )
        )

    @staticmethod
    def _similar(
        candidate: str,
        existing: list[LearningObjective],
    ) -> bool:
        candidate_tokens = set(
            candidate.casefold().split()
        )

        if not candidate_tokens:
            return True

        for objective in existing:
            existing_tokens = set(
                objective.description.casefold().split()
            )

            overlap = (
                len(
                    candidate_tokens
                    & existing_tokens
                )
                / max(
                    1,
                    len(candidate_tokens),
                )
            )

            if overlap >= 0.75:
                return True

        return False

    def _fallback_candidates(
        self,
        *,
        existing: list[LearningObjective],
        gaps: list[str],
        reflections: list[str],
        failures: list[str],
    ) -> list[CuriosityCandidate]:
        candidates: list[CuriosityCandidate] = []

        for gap in gaps:
            gap = gap.strip()

            if not gap:
                continue

            description = (
                "Investigate the unresolved knowledge gap "
                f"and establish evidence-backed conclusions: {gap}"
            )

            if self._similar(
                description,
                existing,
            ):
                continue

            title = (
                f"Resolve knowledge gap: "
                f"{gap[:80]}"
            )

            candidates.append(
                CuriosityCandidate(
                    objective_id=self._objective_id(
                        title,
                        description,
                    ),
                    title=title,
                    description=description,
                    priority=90,
                    rationale=(
                        "Generated from an explicit "
                        "knowledge gap."
                    ),
                    novelty=0.9,
                    information_gain=0.9,
                    difficulty=0.4,
                )
            )

        for failure in failures:
            failure = failure.strip()

            if not failure:
                continue

            description = (
                "Investigate the cause of the previous "
                f"learning failure and identify a reliable "
                f"way to avoid it: {failure}"
            )

            if self._similar(
                description,
                existing,
            ):
                continue

            title = (
                "Failure recovery: "
                f"{failure[:80]}"
            )

            candidates.append(
                CuriosityCandidate(
                    objective_id=self._objective_id(
                        title,
                        description,
                    ),
                    title=title,
                    description=description,
                    priority=85,
                    rationale=(
                        "Generated from a previous "
                        "learning failure."
                    ),
                    novelty=0.8,
                    information_gain=0.85,
                    difficulty=0.5,
                )
            )

        for reflection in reflections:
            reflection = reflection.strip()

            if not reflection:
                continue

            description = (
                "Explore an unresolved implication or "
                "follow-up question identified by a "
                f"previous reflection: {reflection}"
            )

            if self._similar(
                description,
                existing,
            ):
                continue

            title = (
                "Reflection follow-up: "
                f"{reflection[:80]}"
            )

            candidates.append(
                CuriosityCandidate(
                    objective_id=self._objective_id(
                        title,
                        description,
                    ),
                    title=title,
                    description=description,
                    priority=70,
                    rationale=(
                        "Generated from a previous "
                        "reflection."
                    ),
                    novelty=0.75,
                    information_gain=0.8,
                    difficulty=0.5,
                )
            )

        return candidates[
            : self.max_candidates
        ]

    async def generate(
        self,
        *,
        existing: list[LearningObjective],
        gaps: list[str] | None = None,
        reflections: list[str] | None = None,
        failures: list[str] | None = None,
    ) -> list[CuriosityCandidate]:
        gaps = list(gaps or [])
        reflections = list(reflections or [])
        failures = list(failures or [])

        if self.llm is None:
            return self._fallback_candidates(
                existing=existing,
                gaps=gaps,
                reflections=reflections,
                failures=failures,
            )

        existing_text = "\n".join(
            (
                f"- {item.title or item.objective_id}: "
                f"{item.description}"
            )
            for item in existing[:20]
        )

        gaps_text = "\n".join(
            f"- {item}"
            for item in gaps[:20]
        )

        reflections_text = "\n".join(
            f"- {item}"
            for item in reflections[:10]
        )

        failures_text = "\n".join(
            f"- {item}"
            for item in failures[:10]
        )

        prompt = f"""
You are AURA's curiosity and curriculum planner.

Generate a SMALL set of high-value next learning objectives.

Prioritize:
1. unresolved knowledge gaps
2. lessons from failed runs
3. follow-ups implied by reflections
4. novel but relevant unexplored areas
5. objectives with high expected information gain

Avoid:
- duplicates
- trivial rephrasing
- broad/vague objectives
- objectives unrelated to the existing curriculum
- objectives requiring unsafe or unauthorized actions

Each objective must be independently researchable.

Return ONLY valid JSON:
{{
  "candidates": [
    {{
      "title": "string",
      "description": "string",
      "priority": 0,
      "rationale": "string",
      "novelty": 0.0,
      "information_gain": 0.0,
      "difficulty": 0.0
    }}
  ]
}}

EXISTING OBJECTIVES:
{existing_text or "none"}

KNOWLEDGE GAPS:
{gaps_text or "none"}

PREVIOUS REFLECTIONS:
{reflections_text or "none"}

PREVIOUS FAILURES:
{failures_text or "none"}
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
        except json.JSONDecodeError:
            return self._fallback_candidates(
                existing=existing,
                gaps=gaps,
                reflections=reflections,
                failures=failures,
            )

        if not isinstance(payload, dict):
            return []

        raw_candidates = payload.get(
            "candidates",
            [],
        )

        if not isinstance(
            raw_candidates,
            list,
        ):
            return []

        candidates: list[CuriosityCandidate] = []

        for item in raw_candidates:
            if not isinstance(item, dict):
                continue

            title = str(
                item.get("title", "")
            ).strip()

            description = str(
                item.get("description", "")
            ).strip()

            if not title or not description:
                continue

            if self._similar(
                description,
                existing,
            ):
                continue

            try:
                priority = int(
                    item.get(
                        "priority",
                        50,
                    )
                )
            except (TypeError, ValueError):
                priority = 50

            def bounded_float(
                key: str,
                default: float,
            ) -> float:
                try:
                    value = float(
                        item.get(
                            key,
                            default,
                        )
                    )
                except (TypeError, ValueError):
                    value = default

                return max(
                    0.0,
                    min(1.0, value),
                )

            candidates.append(
                CuriosityCandidate(
                    objective_id=self._objective_id(
                        title,
                        description,
                    ),
                    title=title,
                    description=description,
                    priority=max(
                        0,
                        min(100, priority),
                    ),
                    rationale=str(
                        item.get(
                            "rationale",
                            "",
                        )
                    ).strip(),
                    novelty=bounded_float(
                        "novelty",
                        0.5,
                    ),
                    information_gain=bounded_float(
                        "information_gain",
                        0.5,
                    ),
                    difficulty=bounded_float(
                        "difficulty",
                        0.5,
                    ),
                )
            )

            if len(candidates) >= self.max_candidates:
                break

        return sorted(
            candidates,
            key=lambda item: (
                -(
                    item.priority
                    + (
                        item.novelty
                        * 20
                    )
                    + (
                        item.information_gain
                        * 20
                    )
                    - (
                        item.difficulty
                        * 10
                    )
                ),
                item.objective_id,
            ),
        )

    @staticmethod
    def to_objective(
        candidate: CuriosityCandidate,
    ) -> LearningObjective:
        return LearningObjective(
            objective_id=candidate.objective_id,
            title=candidate.title,
            description=candidate.description,
            priority=candidate.priority,
            enabled=True,
        )
