import pytest

from aura_core.application.adaptive_execution import (
    AdaptiveExecutionController,
    RecoveryAction,
    StepObservation,
)
from aura_core.application.proactive_events import ProactiveEventObserver
from aura_core.kernel.events import KernelEvent


def test_retryable_failure_allows_only_bounded_replan() -> None:
    controller = AdaptiveExecutionController(max_replans=1)
    first = controller.decide(
        StepObservation("search", succeeded=False, retryable=True),
        replan_count=0,
    )
    assert first.action is RecoveryAction.REPLAN_ONCE
    assert first.replan_count == 1

    second = controller.decide(
        StepObservation("search", succeeded=False, retryable=True),
        replan_count=1,
    )
    assert second.action is RecoveryAction.STOP
    assert second.replan_count == 1


def test_authorization_denial_never_triggers_replanning() -> None:
    decision = AdaptiveExecutionController().decide(
        StepObservation("search", succeeded=False, retryable=True, authorization_denied=True),
        replan_count=0,
    )
    assert decision.action is RecoveryAction.STOP


def test_side_effecting_failure_requires_human_action() -> None:
    decision = AdaptiveExecutionController().decide(
        StepObservation("publish", succeeded=False, side_effecting=True, retryable=True),
        replan_count=0,
    )
    assert decision.action is RecoveryAction.REQUIRE_APPROVAL


def test_controller_caps_replan_budget() -> None:
    with pytest.raises(ValueError):
        AdaptiveExecutionController(max_replans=3)


def test_proactive_observer_only_emits_allowlisted_suggestions() -> None:
    observer = ProactiveEventObserver()
    event = KernelEvent(
        event_type="ServiceFailed",
        source_component="test",
        payload={"task_id": "task-123", "instruction": "execute arbitrary command"},
        correlation_id="corr-1",
    )
    suggestion = observer.observe(event)
    assert suggestion is not None
    assert suggestion.requires_user_action is True
    assert "task-123" in suggestion.summary
    assert "arbitrary command" not in suggestion.summary
    assert observer.observe(KernelEvent(event_type="UnknownEvent", source_component="test")) is None
