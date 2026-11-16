"""Deterministic research dossier: explicit questions, governed evidence, no claims.

A dossier is NOT a generated factual answer or an autonomous agent. It is an
auditable review packet that can be prepared after all queries are permitted by
the existing MCP Gateway. Source text is untrusted; no LLM/tool instructions
or external requests are executed by this layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from aura_core.kernel.permissions import RiskLevel
from aura_core.research.mcp_source import MCPResearchSource
from aura_core.research.multiquery import (
    ResearchBatch, ResearchFinding, bounded_multiquery_search,
)


@dataclass(frozen=True, slots=True)
class ReviewSection:
    question_index: int
    question: str
    citation_indices: tuple[int, ...]
    distinct_source_hosts: int
    review_status: str


@dataclass(frozen=True, slots=True)
class ResearchDossier:
    question: str
    sections: tuple[ReviewSection, ...]
    evidence: tuple[ResearchFinding, ...]
    complete_search: bool
    authorization_route: str
    factual_claims_verified: bool
    needs_human_review: bool
    safety_status: str = "UNTRUSTED_EVIDENCE"


async def create_research_dossier(
    source: MCPResearchSource,
    *,
    principal_id: str,
    question: str,
    subquestions: list[str] | tuple[str, ...],
    resource_scope: str,
    risk_level: RiskLevel,
    task_id: str,
) -> ResearchDossier:
    """Collect question-indexed source evidence and explicit review gaps.

    All subquestions are caller-provided; model synthesis/planning is a later
    separately governed capability. This function does not infer truth from
    source frequency or automatically mark citations as reliable.
    """
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 500:
        raise ValueError("research question must contain 1..500 characters")
    if question != question.strip() or any(ord(c) < 32 or ord(c) == 127 for c in question):
        raise ValueError("research question contains controls or padding")
    batch: ResearchBatch = await bounded_multiquery_search(
        source, principal_id=principal_id, queries=subquestions,
        resource_scope=resource_scope, risk_level=risk_level, task_id=task_id,
        max_findings=20,
    )
    if not batch.complete or not batch.gateway_routed:
        raise ValueError("research evidence is not fully Gateway authorized")
    if any(item.trust != "UNTRUSTED" for item in batch.findings):
        raise ValueError("research evidence contains an invalid trust designation")

    sections: list[ReviewSection] = []
    for qindex, subquestion in enumerate(batch.queries):
        indexes = tuple(
            idx for idx, finding in enumerate(batch.findings)
            if finding.query_index == qindex
        )
        hosts = {
            urlsplit(batch.findings[idx].url).hostname
            for idx in indexes
        }
        # Host diversity only signals potential independent sources; it is
        # never a credibility, causality, corroboration or truth judgment.
        if not indexes:
            state = "NO_RESULTS"
        elif len(hosts) < 2:
            state = "NEEDS_ADDITIONAL_SOURCES"
        else:
            state = "SOURCE_DIVERSITY_REVIEW_REQUIRED"
        sections.append(ReviewSection(
            question_index=qindex, question=subquestion,
            citation_indices=indexes, distinct_source_hosts=len(hosts),
            review_status=state,
        ))
    return ResearchDossier(
        question=question,
        sections=tuple(sections),
        evidence=batch.findings,
        complete_search=True,
        authorization_route="MCP_GATEWAY",
        factual_claims_verified=False,
        needs_human_review=True,
    )
