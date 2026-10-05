from __future__ import annotations

from collections import defaultdict

from .models import KnowledgeConflict, KnowledgeFact


class KnowledgeGraph:
    def __init__(self) -> None:
        self._facts: dict[str, KnowledgeFact] = {}
        self._by_subject: dict[str, set[str]] = defaultdict(set)
        self._conflicts: dict[str, KnowledgeConflict] = {}

    def add_fact(self, fact: KnowledgeFact) -> None:
        previous = self._facts.get(fact.fact_id)

        if previous is not None:
            self._by_subject[previous.subject].discard(
                previous.fact_id
            )

        self._facts[fact.fact_id] = fact
        self._by_subject[fact.subject].add(fact.fact_id)

    def add_conflict(
        self,
        conflict: KnowledgeConflict,
    ) -> None:
        self._conflicts[conflict.conflict_id] = conflict

    def facts_for(
        self,
        subject: str,
    ) -> list[KnowledgeFact]:
        ids = sorted(
            self._by_subject.get(subject, set())
        )

        return [
            self._facts[fact_id]
            for fact_id in ids
        ]

    def all_facts(self) -> list[KnowledgeFact]:
        return sorted(
            self._facts.values(),
            key=lambda fact: fact.fact_id,
        )

    def conflicts(self) -> list[KnowledgeConflict]:
        return sorted(
            self._conflicts.values(),
            key=lambda conflict: conflict.conflict_id,
        )
