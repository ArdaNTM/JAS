from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ResearchCandidate:
    uri: str
    title: str | None = None
    source_type: str = "unknown"
    content: str = ""
    metadata: dict[str, object] | None = None


class ResearchPlanner:
    def plan_queries(
        self,
        objective: str,
        max_queries: int,
    ) -> list[str]:
        objective = objective.strip()

        if not objective:
            return []

        candidates = [
            objective,
            f"{objective} overview",
            f"{objective} latest developments",
            f"{objective} authoritative documentation",
        ]

        seen: set[str] = set()
        result: list[str] = []

        for query in candidates:
            normalized = query.casefold()

            if normalized in seen:
                continue

            seen.add(normalized)
            result.append(query)

            if len(result) >= max_queries:
                break

        return result

    def record_from_candidate(
        self,
        *,
        namespace: str,
        objective_id: str,
        candidate: ResearchCandidate,
        source_id: str,
    ):
        from ..knowledge.models import KnowledgeRecord

        return KnowledgeRecord.create(
            namespace=namespace,
            content=candidate.content,
            source_id=source_id,
            kind="research",
            title=candidate.title,
            confidence=0.5,
            metadata={
                "objective_id": objective_id,
                "source_type": candidate.source_type,
                **(candidate.metadata or {}),
            },
        )
