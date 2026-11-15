"""Features #10/#62: real topological goal coordination, no execution."""
from __future__ import annotations

from dataclasses import replace

import pytest

from aura_core.application.goal_planning import GoalStep, plan_goal_steps


def example():
    return (
        GoalStep("research", "Gather and review evidence", priority=0, estimated_minutes=60),
        GoalStep("design", "Produce a bounded plan", ("research",), priority=-1, estimated_minutes=30),
        GoalStep("approve", "Request explicit Owner approval", ("design",), estimated_minutes=10),
        GoalStep("outline", "Prepare optional summary", priority=1, estimated_minutes=20),
    )


def project(*, steps=None, completed=()):
    return plan_goal_steps(
        steps or example(), principal_id="owner:1", goal_id="goal-1",
        claimed_completed=completed,
    )


def test_parallel_readiness_and_critical_path_from_real_dependency_graph():
    result = project()
    assert result.current_ready_ids == ("research", "outline")
    assert result.hypothetical_waves == (
        ("research", "outline"), ("design",), ("approve",),
    )
    assert result.estimated_critical_chain_minutes == 100
    assert result.current_blocked_ids == ("design", "approve")
    assert result.ordered_step_ids == ("research", "outline", "design", "approve")
    assert not result.claimed_completion_verified
    assert not result.actions_executed
    assert not result.authorization_checked
    assert not result.owner_approval_verified


def test_deterministic_under_input_reordering():
    assert project(steps=example()) == project(steps=tuple(reversed(example())))


def test_hypothetical_claims_do_not_become_verified_receipts():
    result = project(completed=("research",))
    assert result.current_ready_ids == ("design", "outline")
    assert result.estimated_critical_chain_minutes == 40
    assert not result.claimed_completion_verified
    with pytest.raises(ValueError, match="predecessors"):
        project(completed=("design",))


def test_cycle_and_missing_dependency_rejected():
    with pytest.raises(ValueError, match="cycle"):
        project(steps=(
            GoalStep("a", "A", ("b",)),
            GoalStep("b", "B", ("a",)),
        ))
    with pytest.raises(ValueError, match="missing"):
        project(steps=(GoalStep("a", "A", ("unknown",)),))


def test_duplicate_and_self_dependency_fails_closed():
    with pytest.raises(ValueError, match="duplicate"):
        project(steps=(GoalStep("a", "A"), GoalStep("a", "Another")))
    with pytest.raises(ValueError, match="dependencies"):
        project(steps=(GoalStep("a", "A", ("a",)),))


@pytest.mark.parametrize("bad", [
    GoalStep("root/../../", "Bad ID"),
    GoalStep("a", "x\nescape"),
    GoalStep("a", ""),
    GoalStep("a", "A", priority=True),
    GoalStep("a", "A", estimated_minutes=0),
    GoalStep("a", "A", estimated_minutes=10081),
    GoalStep("a", "A", dependencies=["b"]),
    GoalStep("a", "A", dependencies=("b", "b")),
])
def test_type_and_payload_bounds_rejected(bad):
    with pytest.raises(ValueError):
        project(steps=(bad,))


def test_missing_or_malformed_goal_scope_and_claims_rejected():
    with pytest.raises(ValueError):
        plan_goal_steps(example(), principal_id="../other", goal_id="goal-1")
    with pytest.raises(ValueError):
        project(completed=("unknown",))
    with pytest.raises(ValueError):
        project(completed=("research", "research"))
    with pytest.raises(ValueError):
        project(completed=["research"])


def test_100_step_limit_and_boolean_input():
    with pytest.raises(ValueError):
        project(steps=tuple(GoalStep(f"s{i}", "X") for i in range(101)))
    with pytest.raises(ValueError):
        project(steps=(object(),))


def test_claimed_completion_cannot_hide_a_cycle():
    cyclic = (
        GoalStep("a", "A", ("b",)),
        GoalStep("b", "B", ("a",)),
    )
    with pytest.raises(ValueError, match="cycle"):
        project(steps=cyclic, completed=("a", "b"))
