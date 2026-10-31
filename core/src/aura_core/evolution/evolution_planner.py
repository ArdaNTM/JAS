"""Idle evolution review: explicit opt-in, bounded proposals, no tool execution.

Optional discovery and code-drafting adapters are injected by the owner
composition root. Their outputs are treated as untrusted proposals. The daemon
cannot grant permissions, install dependencies, modify sources, execute a
sandbox job, or activate an MCP tool.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Protocol

from aura_core.application.self_tool_synthesis import CandidateToolValidator, ToolCandidate
from aura_core.evolution.autonomous_analyzer import AutonomousAnalyzer, GoalProposal

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OpenSourceEvidence:
    repository_url: str
    license_id: str
    summary: str


@dataclass(frozen=True, slots=True)
class EvolutionSuggestion:
    suggestion_id: str
    proposal_id: str
    title: str
    evidence: tuple[OpenSourceEvidence, ...]
    candidate_manifest: dict | None = None
    static_validation: dict | None = None
    status: str = "awaiting_local_owner_review"
    execution_performed: bool = False

    def to_dict(self) -> dict:
        result = asdict(self)
        # A candidate's source code is never included in status responses.
        return result


class ReviewedDiscovery(Protocol):
    async def search(self, *, topic: str, limit: int) -> tuple[OpenSourceEvidence, ...]:
        """Read-only evidence from an existing, Gateway-governed search capability."""
        ...


class DraftGenerator(Protocol):
    async def propose(self, *, finding: GoalProposal, sources: tuple[OpenSourceEvidence, ...]) -> ToolCandidate | None:
        """Return a reviewable candidate, not a runnable provider."""
        ...


class EvolutionPlanner:
    def __init__(
        self, analyzer: AutonomousAnalyzer, *,
        discovery: ReviewedDiscovery | None = None,
        drafting: DraftGenerator | None = None,
        idle_seconds: int = 300, interval_seconds: int = 900,
        last_activity: Callable[[], float] = time.monotonic,
        max_suggestions: int = 8, max_cycles: int = 100,
    ) -> None:
        if not 60 <= idle_seconds <= 86400 or not 60 <= interval_seconds <= 86400:
            raise ValueError("Invalid idle/interval budget")
        if not 1 <= max_suggestions <= 20 or not 1 <= max_cycles <= 500:
            raise ValueError("Invalid cycle budget")
        self.analyzer = analyzer
        self.discovery = discovery
        self.drafting = drafting
        self.idle_seconds = idle_seconds
        self.interval_seconds = interval_seconds
        self.last_activity = last_activity
        self.max_suggestions = max_suggestions
        self.max_cycles = max_cycles
        self._task: asyncio.Task[None] | None = None
        self._cycles = 0
        self._errors = 0
        self._backlog: dict[str, EvolutionSuggestion] = {}
        self._validator = CandidateToolValidator()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="aura-evolution-review")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def run_once(self) -> tuple[EvolutionSuggestion, ...]:
        if self._cycles >= self.max_cycles:
            return ()
        if time.monotonic() - self.last_activity() < self.idle_seconds:
            return ()
        report = await asyncio.to_thread(self.analyzer.scan)
        proposals = report.proposals[: self.max_suggestions]
        new_items: list[EvolutionSuggestion] = []
        for proposal in proposals:
            if proposal.proposal_id in self._backlog:
                continue
            evidence: tuple[OpenSourceEvidence, ...] = ()
            if self.discovery is not None:
                try:
                    # The adapter is responsible for MCP Gateway authorization
                    # and an explicit network policy; absence means no network.
                    evidence = tuple((await asyncio.wait_for(
                        self.discovery.search(topic=proposal.category, limit=3),
                        timeout=15,
                    ))[:3])
                    evidence = tuple(item for item in evidence if (
                        isinstance(item, OpenSourceEvidence)
                        and item.repository_url.startswith("https://github.com/")
                        and len(item.repository_url) <= 300
                        and 1 <= len(item.license_id) <= 50
                        and len(item.summary) <= 300
                    ))
                except (asyncio.TimeoutError, ValueError, OSError):
                    logger.warning("Governed discovery unavailable")
            manifest = validation = None
            if self.drafting is not None:
                try:
                    candidate = await asyncio.wait_for(
                        self.drafting.propose(finding=proposal, sources=evidence), timeout=25,
                    )
                    if candidate is not None:
                        validation = self._validator.validate(candidate)
                        manifest = candidate.manifest()
                except (asyncio.TimeoutError, ValueError):
                    logger.warning("Candidate proposal drafting unavailable")
            item = EvolutionSuggestion(
                suggestion_id=hashlib.sha256(
                    ("evolution:" + proposal.proposal_id).encode()
                ).hexdigest()[:24],
                proposal_id=proposal.proposal_id,
                title=proposal.summary,
                evidence=evidence, candidate_manifest=manifest,
                static_validation=validation,
            )
            self._backlog[proposal.proposal_id] = item
            new_items.append(item)
        self._cycles += 1
        return tuple(new_items)

    def list_proposals(self, *, limit: int = 20) -> list[dict]:
        bounded = max(1, min(int(limit), 50))
        return [item.to_dict() for item in list(self._backlog.values())[-bounded:]]

    def status(self) -> dict:
        return {
            "enabled": self._task is not None and not self._task.done(),
            "mode": "review_only",
            "cycles": self._cycles,
            "errors": self._errors,
            "queued": len(self._backlog),
            "max_cycles": self.max_cycles,
            "can_execute": False,
        }

    async def _run(self) -> None:
        while self._cycles < self.max_cycles:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                self._errors += 1
                logger.warning("Evolution review cycle failed")
                if self._errors >= 10:
                    # Stop rather than silently retry forever on persistent failure.
                    return
            await asyncio.sleep(self.interval_seconds)
