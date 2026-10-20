from datetime import UTC, datetime

from aura_core.application.proactive_store import ProactiveSuggestionStore
from aura_core.kernel.events import KernelEvent


def _event(event_type, task_id, correlation_id="plan-1"):
    return KernelEvent(
        event_type=event_type,
        source_component="test",
        payload={"task_id": task_id, "instruction": "never expose this"},
        correlation_id=correlation_id,
        timestamp=datetime.now(UTC),
    )


def test_proactive_store_deduplicates_same_task_event():
    store = ProactiveSuggestionStore()
    first = store.observe(_event("TaskFailed", "task-1"))
    second = store.observe(_event("TaskFailed", "task-1"))
    assert first == second
    assert len(store.list_items()) == 1
    assert "never expose" not in str(first)


def test_proactive_store_ignores_unknown_event_and_bounds_limit():
    store = ProactiveSuggestionStore(max_items=2)
    assert store.observe(_event("UnknownEvent", "task-1")) is None
    store.observe(_event("TaskFailed", "task-1", "plan-1"))
    store.observe(_event("TaskSucceeded", "task-2", "plan-2"))
    store.observe(_event("ServiceFailed", "task-3", "plan-3"))
    assert len(store.list_items()) == 2
