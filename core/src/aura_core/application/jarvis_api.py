"""Local-only HTTP surface for governed JARVIS memory and adaptation."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from aura_core.application.episodic_memory import EpisodicMemoryStore
from aura_core.application.jarvis_intelligence import InitiativeEngine, SelfAdaptationEngine


router = APIRouter(prefix="/api/jarvis", tags=["jarvis-intelligence"])


def _require_local(request: Request) -> None:
    client = request.client
    host = client.host if client is not None else ""
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="Local client required")


def _memory(request: Request) -> EpisodicMemoryStore:
    store = getattr(request.app.state, "episodic_memory", None)
    if store is None:
        store = EpisodicMemoryStore.from_environment()
        request.app.state.episodic_memory = store
    return store


def _adaptation(request: Request) -> SelfAdaptationEngine:
    engine = getattr(request.app.state, "self_adaptation", None)
    if engine is None:
        engine = SelfAdaptationEngine()
        request.app.state.self_adaptation = engine
    return engine


def _initiatives(request: Request) -> InitiativeEngine:
    engine = getattr(request.app.state, "initiative_engine", None)
    if engine is None:
        engine = InitiativeEngine()
        request.app.state.initiative_engine = engine
    return engine


class MemoryWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    principal_id: str = Field(min_length=1, max_length=128)
    kind: Literal["preference", "fact", "episode", "goal", "lesson"]
    content: str = Field(min_length=1, max_length=8000)
    tags: list[str] = Field(default_factory=list, max_length=32)
    source_task_id: str | None = Field(default=None, max_length=128)
    importance: int = Field(default=3, ge=1, le=5)


class AdaptationObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Literal["succeeded", "failed", "cancelled"]
    failure_class: str = Field(default="", max_length=80)
    task_id: str = Field(default="", max_length=128)


class AdaptationProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy_id: str = Field(min_length=1, max_length=100)
    rationale: str = Field(min_length=1, max_length=1000)


class AdaptationApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: bool = False


class InitiativeObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: str = Field(min_length=1, max_length=80)
    correlation_id: str = Field(default="", max_length=128)
    payload: dict[str, object] = Field(default_factory=dict)


@router.post("/memory")
def remember_memory(body: MemoryWrite, request: Request) -> dict[str, object]:
    _require_local(request)
    try:
        record = _memory(request).remember(
            principal_id=body.principal_id,
            kind=body.kind,
            content=body.content,
            tags=body.tags,
            source_task_id=body.source_task_id,
            importance=body.importance,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record.to_dict()


@router.get("/memory")
def recall_memory(
    request: Request,
    principal_id: str,
    query: str = "",
    kind: str | None = None,
    limit: int = 20,
) -> dict[str, object]:
    _require_local(request)
    try:
        records = _memory(request).recall(
            principal_id=principal_id, query=query, kind=kind, limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"items": [record.to_dict() for record in records], "count": len(records)}


@router.delete("/memory/{memory_id}")
def forget_memory(memory_id: str, request: Request, principal_id: str) -> dict[str, bool]:
    _require_local(request)
    deleted = _memory(request).forget(principal_id=principal_id, memory_id=memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory record not found")
    return {"deleted": True}


@router.post("/adaptations/observations")
def observe_outcome(body: AdaptationObservation, request: Request) -> dict[str, object]:
    _require_local(request)
    return _adaptation(request).observe(
        outcome=body.outcome, failure_class=body.failure_class, task_id=body.task_id,
    )


@router.post("/adaptations/proposals")
def propose_adaptation(body: AdaptationProposalRequest, request: Request) -> dict[str, object]:
    _require_local(request)
    try:
        proposal = _adaptation(request).propose(
            strategy_id=body.strategy_id, rationale=body.rationale,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return proposal.to_dict()


@router.get("/adaptations/proposals")
def list_adaptations(request: Request) -> dict[str, object]:
    _require_local(request)
    engine = _adaptation(request)
    return {
        "items": [item.to_dict() for item in engine.proposals()],
        "approved_strategies": list(engine.approved_strategies()),
    }


@router.post("/adaptations/proposals/{proposal_id}/approve")
def approve_adaptation(
    proposal_id: str, body: AdaptationApproval, request: Request,
) -> dict[str, object]:
    _require_local(request)
    if not body.confirmed:
        raise HTTPException(status_code=409, detail="Explicit confirmation required")
    try:
        return _adaptation(request).approve(proposal_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Adaptation proposal not found") from exc


@router.post("/initiatives/observe")
def observe_initiative(body: InitiativeObservation, request: Request) -> dict[str, object]:
    _require_local(request)
    suggestion = _initiatives(request).observe_event(
        event_type=body.event_type,
        correlation_id=body.correlation_id,
        payload=body.payload,
    )
    if suggestion is None:
        raise HTTPException(status_code=422, detail="Event type is not allow-listed")
    return suggestion


@router.get("/initiatives")
def list_initiatives(request: Request, limit: int = 20) -> dict[str, object]:
    _require_local(request)
    items = _initiatives(request).suggestions(limit=limit)
    return {"items": list(items), "count": len(items)}
