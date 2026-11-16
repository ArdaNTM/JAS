"""Two-stage deep-research evidence dossier over the governed multi-query MCP path.

All search requests are explicitly user-supplied and pass through the existing
MCPResearchSource -> MCPGateway -> PermissionEngine. This module never invokes
HTTP directly, executes evidence text, grants new capabilities, or treats URL
metadata as verified facts.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import urlsplit

from aura_core.kernel.permissions import RiskLevel
from aura_core.research.mcp_source import MCPResearchSource
from aura_core.research.multiquery import ResearchBatch, ResearchFinding, bounded_multiquery_search


class DossierIncomplete(RuntimeError):
    """An untrusted or incomplete stage cannot be presented as a dossier."""


@dataclass(frozen=True, slots=True)
class ResearchDossierPlan:
    topic: str
    primary_queries: tuple[str, ...]
    verification_queries: tuple[str, ...]
    required_source_hosts: int = 2
    max_seconds: int = 45

    def __post_init__(self) -> None:
        if (not isinstance(self.topic, str) or not 1 <= len(self.topic) <= 160
                or not self.topic.strip() or self.topic != self.topic.strip()
                or any(ord(char) < 32 or ord(char) == 127 for char in self.topic)):
            raise ValueError("topic must be bounded nonempty text")
        for queries in (self.primary_queries, self.verification_queries):
            if not isinstance(queries, (list, tuple)) or not 1 <= len(queries) <= 3:
                raise ValueError("each research stage requires 1..3 explicit queries")
            if any(not isinstance(q, str) or not q or len(q) > 256
                   or q != q.strip() or any(ord(c) < 32 or ord(c) == 127 for c in q)
                   for q in queries):
                raise ValueError("invalid research stage query")
        object.__setattr__(self, "primary_queries", tuple(self.primary_queries))
        object.__setattr__(self, "verification_queries", tuple(self.verification_queries))
        all_queries = self.primary_queries + self.verification_queries
        if len({q.casefold() for q in all_queries}) != len(all_queries):
            raise ValueError("verification and primary queries must be distinct")
        if type(self.required_source_hosts) is not int or not 1 <= self.required_source_hosts <= 6:
            raise ValueError("required_source_hosts must be 1..6")
        if type(self.max_seconds) is not int or not 1 <= self.max_seconds <= 120:
            raise ValueError("max_seconds must be 1..120")


@dataclass(frozen=True, slots=True)
class DossierEvidence:
    stage: str
    query_index: int
    url: str
    domain: str
    title: str
    snippet: str
    source_label: str
    provider_id: str
    trust: str = "UNTRUSTED"


@dataclass(frozen=True, slots=True)
class ResearchDossier:
    topic: str
    primary_queries: tuple[str, ...]
    verification_queries: tuple[str, ...]
    evidence: tuple[DossierEvidence, ...]
    distinct_hosts: tuple[str, ...]
    repeated_hosts: tuple[str, ...]
    required_source_hosts: int
    insufficient_source_diversity: bool
    output_truncated: bool
    status: str = "EVIDENCE_ONLY_NOT_FACT_CHECKED"


def _assured(stage: object) -> ResearchBatch:
    if not isinstance(stage, ResearchBatch) or stage.complete is not True or stage.gateway_routed is not True:
        raise DossierIncomplete("research stage has no complete Gateway evidence")
    if any(not isinstance(f, ResearchFinding) or f.trust != "UNTRUSTED" for f in stage.findings):
        raise DossierIncomplete("research stage contains unverified evidence semantics")
    return stage


async def build_research_dossier(
    source: MCPResearchSource,
    plan: ResearchDossierPlan,
    *,
    principal_id: str,
    resource_scope: str,
    risk_level: RiskLevel,
    task_id: str,
) -> ResearchDossier:
    """Return an evidence-only dossier after both *independently authorized* stages.

    The second-stage queries come exclusively from the explicit validated plan,
    never from tool output or model-written follow-up instructions. A denial,
    provider error or timeout aborts the entire workflow; no partial dossier
    is returned. Source diversity is an observation, not corroborated truth.
    """
    if not isinstance(source, MCPResearchSource):
        raise TypeError("source must be the existing MCPResearchSource")
    if not isinstance(plan, ResearchDossierPlan):
        raise TypeError("plan must be an immutable ResearchDossierPlan")
    try:
        async with asyncio.timeout(plan.max_seconds):
            primary = _assured(await bounded_multiquery_search(
                source, principal_id=principal_id,
                queries=plan.primary_queries,
                resource_scope=resource_scope, risk_level=risk_level,
                task_id=f"{task_id}:primary", max_findings=12,
            ))
            verification = _assured(await bounded_multiquery_search(
                source, principal_id=principal_id,
                queries=plan.verification_queries,
                resource_scope=resource_scope, risk_level=risk_level,
                task_id=f"{task_id}:verification", max_findings=12,
            ))
    except TimeoutError as exc:
        raise DossierIncomplete("research workflow exceeded its time budget") from exc

    items: list[DossierEvidence] = []
    seen_urls: set[str] = set()
    primary_hosts: set[str] = set()
    verification_hosts: set[str] = set()
    output_truncated = False

    for stage_name, batch, stage_hosts in (
        ("primary", primary, primary_hosts),
        ("verification", verification, verification_hosts),
    ):
        for finding in batch.findings:
            # URLs have already passed _public_reference_url in the existing
            # authorized multiquery module. This is a read-only metadata parse.
            domain = urlsplit(finding.url).hostname or ""
            if not domain:
                raise DossierIncomplete("research evidence has no hostname")
            stage_hosts.add(domain.casefold())
            if finding.url in seen_urls:
                continue
            seen_urls.add(finding.url)
            if len(items) >= 18:
                output_truncated = True
                continue
            items.append(DossierEvidence(
                stage=stage_name, query_index=finding.query_index,
                url=finding.url, domain=domain.casefold(),
                title=finding.title, snippet=finding.snippet,
                source_label=finding.source_label,
                provider_id=finding.provider_id,
            ))

    hosts = tuple(sorted(primary_hosts | verification_hosts))
    repeated = tuple(sorted(primary_hosts & verification_hosts))
    return ResearchDossier(
        topic=plan.topic,
        primary_queries=tuple(plan.primary_queries),
        verification_queries=tuple(plan.verification_queries),
        evidence=tuple(items),
        distinct_hosts=hosts,
        repeated_hosts=repeated,
        required_source_hosts=plan.required_source_hosts,
        insufficient_source_diversity=len(hosts) < plan.required_source_hosts,
        output_truncated=output_truncated,
    )
