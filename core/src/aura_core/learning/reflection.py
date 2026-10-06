from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from aura_core.memory.models import MemoryRecord
from aura_core.models.multi_router import LLMProvider


@dataclass(frozen=True, slots=True)
class ReflectionInput:
    run_id: str
    objective_id: str
    objective_title: str
    objective_description: str
    status: str
    steps: int
    sources: int
    records: int
    error: str | None = None
    facts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReflectionResult:
    reflection_id: str
    run_id: str
    summary: str
    insights: tuple[str, ...]
    lessons: tuple[str, ...]
    mistakes: tuple[str, ...]
    next_actions: tuple[str, ...]
    confidence: float
    created_at: datetime

    def as_text(self) -> str:
        sections = [
            f"Summary: {self.summary}",
            "Insights:",
            *(
                f"- {item}"
                for item in self.insights
            ),
            "Lessons:",
            *(
                f"- {item}"
                for item in self.lessons
            ),
            "Mistakes:",
            *(
                f"- {item}"
                for item in self.mistakes
            ),
            "Next actions:",
            *(
                f"- {item}"
                for item in self.next_actions
            ),
            f"Confidence: {self.confidence:.3f}",
        ]

        return "\n".join(sections)


class ReflectionSynthesizer:
    """
    Converts a completed learning episode into a bounded,
    machine-readable reflection.

    Reflection is linguistic memory, not weight modification.
    """

    def __init__(
        self,
        *,
        llm: LLMProvider,
        max_items: int = 5,
    ) -> None:
        if max_items < 1:
            raise ValueError(
                "max_items must be positive"
            )

        self.llm = llm
        self.max_items = max_items

    def _prompt(
        self,
        episode: ReflectionInput,
    ) -> str:
        facts = "\n".join(
            f"- {fact}"
            for fact in episode.facts[
                : self.max_items * 4
            ]
        )

        return f"""
You are AURA's reflection synthesizer.

Analyze ONE completed learning episode.

Do not invent facts.
Do not claim that an action succeeded unless the episode says so.
Distinguish observations from lessons.
Keep every list short and actionable.

Return ONLY valid JSON with this exact schema:
{{
  "summary": "string",
  "insights": ["string"],
  "lessons": ["string"],
  "mistakes": ["string"],
  "next_actions": ["string"],
  "confidence": 0.0
}}

Episode:
run_id: {episode.run_id}
objective_id: {episode.objective_id}
title: {episode.objective_title}
objective: {episode.objective_description}
status: {episode.status}
steps: {episode.steps}
sources: {episode.sources}
records: {episode.records}
error: {episode.error or "none"}

Observed facts:
{facts or "- none"}
""".strip()

    async def reflect(
        self,
        episode: ReflectionInput,
    ) -> ReflectionResult:
        raw = await self.llm.generate(
            self._prompt(episode),
            options={
                "temperature": 0,
                "format": "json",
            },
        )

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Reflection model returned invalid JSON"
            ) from exc

        if not isinstance(payload, dict):
            raise RuntimeError(
                "Reflection model returned a non-object"
            )

        def values(key: str) -> tuple[str, ...]:
            value = payload.get(key, [])

            if not isinstance(value, list):
                return ()

            return tuple(
                str(item).strip()
                for item in value
                if str(item).strip()
            )[: self.max_items]

        try:
            confidence = float(
                payload.get("confidence", 0.5)
            )
        except (TypeError, ValueError):
            confidence = 0.5

        confidence = max(
            0.0,
            min(1.0, confidence),
        )

        summary = str(
            payload.get(
                "summary",
                "",
            )
        ).strip()

        if not summary:
            summary = (
                f"Learning run {episode.run_id} "
                f"completed with status {episode.status}."
            )

        reflection_id = str(
            uuid5(
                NAMESPACE_URL,
                (
                    "aura-reflection:"
                    f"{episode.run_id}"
                ),
            )
        )

        return ReflectionResult(
            reflection_id=reflection_id,
            run_id=episode.run_id,
            summary=summary,
            insights=values("insights"),
            lessons=values("lessons"),
            mistakes=values("mistakes"),
            next_actions=values("next_actions"),
            confidence=confidence,
            created_at=datetime.now(timezone.utc),
        )


def reflection_memory_record(
    result: ReflectionResult,
    *,
    objective_id: str,
) -> MemoryRecord:
    return MemoryRecord(
        record_id=result.reflection_id,
        namespace="episodic",
        content=result.as_text(),
        source=f"learning-run:{result.run_id}",
        metadata={
            "type": "reflection",
            "run_id": result.run_id,
            "objective_id": objective_id,
            "confidence": str(
                result.confidence
            ),
        },
        created_at=result.created_at,
    )
