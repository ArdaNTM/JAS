from __future__ import annotations

from dataclasses import dataclass

from aura_core.learning.self_improvement import (
    ImprovementDecision,
    LearningMetrics,
    PolicyBounds,
    SelfImprovementController,
)


@dataclass(frozen=True)
class FakePolicy:
    max_queries: int = 20
    max_fetches: int = 10
    max_new_records: int = 10
    interval_seconds: float = 100.0


def test_phase11_stable_success_can_propose_bounded_improvement():
    controller = SelfImprovementController(
        bounds=PolicyBounds(
            min_queries=5,
            max_queries=30,
            min_fetches=2,
            max_fetches=20,
            min_new_records=2,
            max_new_records=20,
            min_interval_seconds=10.0,
            max_interval_seconds=300.0,
            max_step_ratio=0.20,
            min_sample_size=5,
        )
    )

    policy = FakePolicy()

    metrics = LearningMetrics(
        total_runs=20,
        successful_runs=19,
        failed_runs=1,
        consecutive_failures=0,
        admission_rate=0.95,
    )

    proposal = controller.propose(
        policy,
        metrics,
    )

    assert proposal.decision is (
        ImprovementDecision.PROPOSED
    )

    assert proposal.candidate_policy.max_queries <= 30
    assert proposal.candidate_policy.max_fetches <= 20
    assert proposal.candidate_policy.max_new_records <= 20
    assert (
        proposal.candidate_policy.interval_seconds
        >= 10.0
    )


def test_phase11_instability_reduces_budget_and_increases_interval():
    controller = SelfImprovementController(
        bounds=PolicyBounds(
            min_queries=5,
            max_queries=100,
            min_fetches=2,
            max_fetches=100,
            min_new_records=2,
            max_new_records=100,
            min_interval_seconds=10.0,
            max_interval_seconds=300.0,
            max_step_ratio=0.20,
            max_consecutive_failures=3,
            min_sample_size=5,
        )
    )

    policy = FakePolicy(
        max_queries=50,
        max_fetches=20,
        max_new_records=20,
        interval_seconds=60.0,
    )

    metrics = LearningMetrics(
        total_runs=10,
        successful_runs=3,
        failed_runs=7,
        consecutive_failures=5,
        admission_rate=0.40,
    )

    proposal = controller.propose(
        policy,
        metrics,
    )

    assert proposal.decision is (
        ImprovementDecision.PROPOSED
    )

    assert (
        proposal.candidate_policy.max_queries
        < policy.max_queries
    )

    assert (
        proposal.candidate_policy.max_fetches
        < policy.max_fetches
    )

    assert (
        proposal.candidate_policy.max_new_records
        < policy.max_new_records
    )

    assert (
        proposal.candidate_policy.interval_seconds
        > policy.interval_seconds
    )


def test_phase11_insufficient_evidence_is_noop():
    controller = SelfImprovementController(
        bounds=PolicyBounds(
            min_sample_size=10
        )
    )

    proposal = controller.propose(
        FakePolicy(),
        LearningMetrics(
            total_runs=9,
            successful_runs=9,
            failed_runs=0,
        ),
    )

    assert proposal.decision is (
        ImprovementDecision.NOOP
    )


def test_phase11_bounds_are_hard():
    controller = SelfImprovementController(
        bounds=PolicyBounds(
            min_queries=10,
            max_queries=21,
            min_fetches=5,
            max_fetches=11,
            min_new_records=5,
            max_new_records=11,
            min_interval_seconds=10.0,
            max_interval_seconds=101.0,
            max_step_ratio=1.0,
            min_sample_size=1,
        )
    )

    proposal = controller.propose(
        FakePolicy(
            max_queries=20,
            max_fetches=10,
            max_new_records=10,
            interval_seconds=100.0,
        ),
        LearningMetrics(
            total_runs=100,
            successful_runs=100,
            failed_runs=0,
            admission_rate=1.0,
        ),
    )

    candidate = proposal.candidate_policy

    assert 10 <= candidate.max_queries <= 21
    assert 5 <= candidate.max_fetches <= 11
    assert 5 <= candidate.max_new_records <= 11
    assert (
        10.0
        <= candidate.interval_seconds
        <= 101.0
    )


def test_phase11_accept_and_rollback_are_deterministic():
    controller = SelfImprovementController(
        bounds=PolicyBounds(
            min_sample_size=1,
            max_queries=30,
            max_fetches=20,
            max_new_records=20,
            max_interval_seconds=300.0,
        )
    )

    policy = FakePolicy()

    metrics = LearningMetrics(
        total_runs=10,
        successful_runs=10,
        failed_runs=0,
        admission_rate=1.0,
    )

    proposal = controller.propose(
        policy,
        metrics,
    )

    accepted = controller.accept(
        proposal
    )

    assert accepted.decision is (
        ImprovementDecision.ACCEPTED
    )

    assert controller.generation == 1
    assert len(
        controller.history()
    ) == 1

    rollback = controller.rollback(
        accepted.candidate_policy
    )

    assert rollback is not None
    assert rollback.decision is (
        ImprovementDecision.ROLLED_BACK
    )

    assert rollback.candidate_policy == (
        accepted.candidate_policy
    )


def test_phase11_no_authority_expansion():
    controller = SelfImprovementController(
        bounds=PolicyBounds(
            min_sample_size=1,
            max_queries=30,
        )
    )

    policy = FakePolicy()

    proposal = controller.propose(
        policy,
        LearningMetrics(
            total_runs=20,
            successful_runs=20,
            failed_runs=0,
        ),
    )

    assert not hasattr(
        proposal.candidate_policy,
        "permission_policy",
    )

    assert not hasattr(
        proposal.candidate_policy,
        "capability_registry",
    )

    assert not hasattr(
        proposal.candidate_policy,
        "provider_registry",
    )
