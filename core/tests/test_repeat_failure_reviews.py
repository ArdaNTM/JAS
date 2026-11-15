"""Feature #12: bounded repeat-failure evidence never grants new authority."""
from __future__ import annotations

import pytest

from aura_core.application.jarvis_intelligence import SelfAdaptationEngine


def test_repeated_failures_are_review_only_and_deduplicated():
    engine = SelfAdaptationEngine()
    engine.observe(outcome="failed", failure_class="timeout", task_id="task-1")
    engine.observe(outcome="failed", failure_class="timeout", task_id="task-1")
    assert engine.repeated_failure_reviews() == ()
    engine.observe(outcome="failed", failure_class="timeout", task_id="task-2")
    results = engine.repeated_failure_reviews()
    assert len(results) == 1
    assert results[0]["failure_class"] == "timeout"
    assert results[0]["unique_failed_tasks"] == 2
    assert results[0]["suggested_strategy"] == "retry_transient_transport_once"
    assert results[0]["can_execute"] is False
    assert results[0]["requires_owner_review"] is True
    assert engine.approved_strategies() == ()
    assert engine.proposals() == ()


def test_authorization_and_validation_failures_never_suggest_bypass():
    engine = SelfAdaptationEngine()
    for number in range(2):
        engine.observe(
            outcome="failed", failure_class="authorization_denied",
            task_id=f"denial-{number}",
        )
        engine.observe(
            outcome="failed", failure_class="validation_error",
            task_id=f"validation-{number}",
        )
    rows = engine.repeated_failure_reviews()
    assert len(rows) == 2
    assert all(item["suggested_strategy"] is None for item in rows)
    assert all(item["can_execute"] is False for item in rows)
    assert engine.approved_strategies() == ()


def test_free_form_error_and_task_identifiers_are_not_exposed():
    engine = SelfAdaptationEngine()
    for number in range(3):
        engine.observe(
            outcome="failed",
            failure_class="token-SECRET-must-not-be-returned",
            task_id=f"SECRET-task-{number}",
        )
    engine.observe(outcome="failed", failure_class="timeout", task_id="")
    engine.observe(outcome="succeeded", failure_class="timeout", task_id="ok")
    assert engine.repeated_failure_reviews() == ()
    assert "SECRET" not in repr(engine.repeated_failure_reviews())


def test_only_latest_bounded_500_observations_count():
    engine = SelfAdaptationEngine()
    engine.observe(outcome="failed", failure_class="timeout", task_id="old-1")
    engine.observe(outcome="failed", failure_class="timeout", task_id="old-2")
    for number in range(500):
        engine.observe(outcome="succeeded", task_id=f"success-{number}")
    assert engine.repeated_failure_reviews() == ()
    for number in range(3):
        engine.observe(
            outcome="failed", failure_class="provider_unavailable",
            task_id=f"new-{number}",
        )
    assert engine.repeated_failure_reviews()[0]["unique_failed_tasks"] == 3


@pytest.mark.parametrize("kwargs", [
    {"min_occurrences": True}, {"min_occurrences": 1},
    {"min_occurrences": 501}, {"limit": 0}, {"limit": False},
    {"limit": 21},
])
def test_review_budgets_fail_closed(kwargs):
    with pytest.raises(ValueError):
        SelfAdaptationEngine().repeated_failure_reviews(**kwargs)
