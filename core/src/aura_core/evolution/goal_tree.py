"""Bounded, deterministic Goal Tree derived from local static evidence.

A goal tree is a review artifact, never a standing permission for self-change.
It contains no raw source, user messages, prompts, log lines or executable code.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, asdict
from collections import defaultdict

from aura_core.evolution.autonomous_analyzer import GoalProposal

_CATEGORIES = {
    "syntax_error": "source_correctness",
    "silent_failure": "runtime_reliability",
    "maintenance_marker": "maintenance",
    "log_timeout": "runtime_reliability",
    "log_exception": "runtime_reliability",
    "log_startup_failure": "runtime_reliability",
}


@dataclass(frozen=True, slots=True)
class GoalGroup:
    goal_id: str
    category: str
    evidence_count: int
    proposal_ids: tuple[str, ...]
    requires_owner_review: bool = True


@dataclass(frozen=True, slots=True)
class GoalTree:
    root_goal: str
    groups: tuple[GoalGroup, ...]
    proposal_count: int
    tree_sha256: str
    mode: str = "read_only_proposals"
    authorization_granted: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class GoalTreeBuilder:
    """Summarize at most 100 unique, evidence-backed improvement opportunities."""

    def build(self, proposals: tuple[GoalProposal, ...] | list[GoalProposal]) -> GoalTree:
        if len(proposals) > 100:
            raise ValueError("Goal tree proposal budget exceeded")
        grouped: dict[str, set[str]] = defaultdict(set)
        for proposal in proposals:
            if not proposal.review_required or proposal.execution_performed:
                raise ValueError("Only pending, non-executed findings are eligible")
            if len(proposal.proposal_id) != 24 or len(proposal.evidence_sha256) != 64:
                raise ValueError("Finding has an invalid evidence identity")
            category = _CATEGORIES.get(proposal.category, "capability_review")
            grouped[category].add(proposal.proposal_id)
        groups = tuple(
            GoalGroup(
                goal_id=hashlib.sha256(("goal:" + name).encode()).hexdigest()[:24],
                category=name,
                evidence_count=len(grouped[name]),
                proposal_ids=tuple(sorted(grouped[name])),
            )
            for name in sorted(grouped)
        )
        identity = "\n".join(
            group.category + ":" + ",".join(group.proposal_ids)
            for group in groups
        )
        return GoalTree(
            root_goal="Improve AURA within JAS governance",
            groups=groups, proposal_count=sum(g.evidence_count for g in groups),
            tree_sha256=hashlib.sha256(identity.encode()).hexdigest(),
        )
