from __future__ import annotations

from aura_core.application.jarvis_intelligence import InitiativeEngine, SelfAdaptationEngine


def test_adaptation_rejects_unreviewed_strategy_and_requires_approval() -> None:
    engine = SelfAdaptationEngine()
    engine.observe(outcome="failed", failure_class="timeout", task_id="task-1")

    try:
        engine.propose(strategy_id="execute_arbitrary_python", rationale="unsafe")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown strategies must be rejected")

    proposal = engine.propose(
        strategy_id="retry_transient_transport_once",
        rationale="A bounded retry can recover from a transient transport timeout.",
    )
    assert proposal.status == "pending"
    assert engine.approved_strategies() == ()

    approved = engine.approve(proposal.proposal_id)
    assert approved.status == "approved"
    assert engine.approved_strategies() == ("retry_transient_transport_once",)


def test_adaptation_deduplicates_proposals_and_bounds_observations() -> None:
    engine = SelfAdaptationEngine()
    first = engine.propose(
        strategy_id="summarize_evidence_before_response",
        rationale="Consistent evidence summaries improve response quality.",
    )
    second = engine.propose(
        strategy_id="summarize_evidence_before_response",
        rationale="Consistent evidence summaries improve response quality.",
    )
    assert first.proposal_id == second.proposal_id

    for index in range(520):
        engine.observe(outcome="succeeded", task_id=f"task-{index}")
    assert len(engine.observations()) == 500


def test_initiative_engine_is_allowlisted_deduplicated_and_non_executing() -> None:
    engine = InitiativeEngine()
    assert engine.observe_event(event_type="UnknownEvent") is None

    first = engine.observe_event(
        event_type="TaskFailed",
        correlation_id="correlation-1",
        payload={"task_id": "task-1", "secret": "must not be copied"},
    )
    second = engine.observe_event(
        event_type="TaskFailed",
        correlation_id="correlation-1",
        payload={"task_id": "task-1"},
    )
    assert first is not None
    assert first == second
    assert first["requires_user_review"] is True
    assert first["can_execute"] is False
    assert "secret" not in repr(first)


def test_episodic_memory_is_scoped_searchable_and_deletable(tmp_path) -> None:
    from aura_core.application.episodic_memory import EpisodicMemoryStore

    store = EpisodicMemoryStore(tmp_path / "memory.sqlite3")
    alice = store.remember(
        principal_id="alice",
        kind="preference",
        content="Prefer concise Turkish summaries.",
        tags=["language", "style"],
        importance=5,
    )
    store.remember(
        principal_id="bob",
        kind="fact",
        content="This record belongs to another principal.",
    )

    assert len(store.recall(principal_id="alice", query="Turkish")) == 1
    assert store.recall(principal_id="bob", query="Turkish") == []
    assert store.count(principal_id="alice") == 1
    assert store.forget(principal_id="bob", memory_id=alice.memory_id) is False
    assert store.forget(principal_id="alice", memory_id=alice.memory_id) is True
    assert store.count(principal_id="alice") == 0
