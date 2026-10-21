"""Governed self-adaptation and initiative proposals.

This layer learns only from bounded structured outcomes. It can propose known,
reviewable execution strategies, but cannot generate/import code, install
packages, grant permissions, or execute tools. Tool execution remains owned by
AgentTaskService -> AgentExecutor -> MCPGateway.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any


ALLOWED_STRATEGIES = {
    "retry_transient_transport_once",
    "prefer_healthier_registered_provider",
    "split_independent_read_only_research",
    "summarize_evidence_before_response",
}


@dataclass(frozen=True, slots=True)
class AdaptationProposal:
    proposal_id: str
    strategy_id: str
    rationale: str
    evidence_count: int
    status: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "strategy_id": self.strategy_id,
            "rationale": self.rationale,
            "evidence_count": self.evidence_count,
            "status": self.status,
            "created_at": self.created_at,
        }


class SelfAdaptationEngine:
    """A deterministic, proposal-first adaptation ledger."""

    def __init__(self) -> None:
        self._observations: list[dict[str, Any]] = []
        self._proposals: dict[str, AdaptationProposal] = {}
        self._approved_strategies: set[str] = set()

    def observe(self, *, outcome: str, failure_class: str = "", task_id: str = "") -> dict[str, Any]:
        if outcome not in {"succeeded", "failed", "cancelled"}:
            raise ValueError("Unsupported task outcome")
        if len(failure_class) > 80 or len(task_id) > 128:
            raise ValueError("Observation fields exceed limits")
        record = {
            "outcome": outcome,
            "failure_class": failure_class,
            "task_id": task_id,
            "observed_at": datetime.now(UTC).isoformat(),
        }
        self._observations.append(record)
        self._observations = self._observations[-500:]
        return dict(record)

    def propose(self, *, strategy_id: str, rationale: str) -> AdaptationProposal:
        if strategy_id not in ALLOWED_STRATEGIES:
            raise ValueError("Strategy is not in the reviewed allow-list")
        rationale = rationale.strip()
        if not rationale or len(rationale) > 1000:
            raise ValueError("Rationale must contain 1..1000 characters")
        evidence_count = len(self._observations)
        fingerprint = sha256(
            f"{strategy_id}\n{rationale}\n{evidence_count}".encode("utf-8")
        ).hexdigest()[:20]
        proposal_id = f"adapt-{fingerprint}"
        existing = self._proposals.get(proposal_id)
        if existing:
            return existing
        proposal = AdaptationProposal(
            proposal_id=proposal_id,
            strategy_id=strategy_id,
            rationale=rationale,
            evidence_count=evidence_count,
            status="pending",
            created_at=datetime.now(UTC).isoformat(),
        )
        self._proposals[proposal_id] = proposal
        return proposal

    def proposals(self) -> tuple[AdaptationProposal, ...]:
        return tuple(self._proposals[key] for key in sorted(self._proposals))

    def approve(self, proposal_id: str) -> AdaptationProposal:
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            raise KeyError(proposal_id)
        if proposal.status == "approved":
            return proposal
        approved = AdaptationProposal(
            proposal_id=proposal.proposal_id,
            strategy_id=proposal.strategy_id,
            rationale=proposal.rationale,
            evidence_count=proposal.evidence_count,
            status="approved",
            created_at=proposal.created_at,
        )
        self._proposals[proposal_id] = approved
        self._approved_strategies.add(proposal.strategy_id)
        return approved

    def approved_strategies(self) -> tuple[str, ...]:
        return tuple(sorted(self._approved_strategies))

    def observations(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(item) for item in self._observations)


class InitiativeEngine:
    """Projects allow-listed events into deduplicated, non-executing suggestions."""

    _RULES = {
        "TaskFailed": (
            "review_failed_task",
            "A task failed; inspect its error and decide whether to retry or revise it.",
        ),
        "TaskSucceeded": (
            "capture_task_lesson",
            "A task completed; consider saving the result or a reusable lesson.",
        ),
        "CapabilityDiscovered": (
            "review_capability_proposal",
            "A capability was discovered; review its manifest and permissions before use.",
        ),
        "ProviderDegraded": (
            "review_provider_health",
            "A provider became degraded; inspect health before routing new work to it.",
        ),
    }

    def __init__(self) -> None:
        self._suggestions: dict[str, dict[str, Any]] = {}

    def observe_event(self, *, event_type: str, correlation_id: str = "", payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
        rule = self._RULES.get(event_type)
        if rule is None:
            return None
        safe_payload = payload or {}
        # Store only small, non-secret identifiers; never echo arbitrary event payloads.
        task_id = str(safe_payload.get("task_id", ""))[:128]
        key_material = f"{event_type}:{correlation_id or task_id}"
        suggestion_id = sha256(key_material.encode("utf-8")).hexdigest()[:24]
        if suggestion_id in self._suggestions:
            return dict(self._suggestions[suggestion_id])
        category, text = rule
        suggestion = {
            "suggestion_id": suggestion_id,
            "category": category,
            "text": text,
            "event_type": event_type,
            "task_id": task_id or None,
            "created_at": datetime.now(UTC).isoformat(),
            "requires_user_review": True,
            "can_execute": False,
        }
        self._suggestions[suggestion_id] = suggestion
        if len(self._suggestions) > 100:
            oldest = next(iter(self._suggestions))
            del self._suggestions[oldest]
        return dict(suggestion)

    def suggestions(self, *, limit: int = 20) -> tuple[dict[str, Any], ...]:
        limit = max(1, min(int(limit), 100))
        return tuple(dict(item) for item in list(self._suggestions.values())[-limit:])
