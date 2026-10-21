from __future__ import annotations

import pytest

from aura_core.memory.hierarchical_memory import (
    ContextItem,
    SQLiteEpisodicMemory,
    WorkingContext,
)


def test_working_context_is_bounded_and_marks_content_untrusted():
    context = WorkingContext(max_items=3, max_chars=8)
    context.add(ContextItem(kind="observation", content="1234"))
    context.add(ContextItem(kind="observation", content="5678"))
    context.add(ContextItem(kind="observation", content="9"))

    snapshot = context.snapshot()
    assert [item.content for item in snapshot] == ["5678", "9"]
    assert all(item.untrusted for item in snapshot)


def test_working_context_truncates_single_oversized_item():
    context = WorkingContext(max_items=2, max_chars=4)
    context.add(ContextItem(kind="goal", content="abcdef"))
    assert [item.content for item in context.snapshot()] == ["abcd"]


def test_episodic_memory_is_scoped_and_append_only(tmp_path):
    store = SQLiteEpisodicMemory(tmp_path / "episodes.sqlite3")
    first = store.append(
        principal_id="alice",
        task_id="task-1",
        content="observed result",
        source="test",
        metadata={"kind": "observation"},
    )
    store.append(
        principal_id="bob",
        task_id="task-1",
        content="private record",
        source="test",
    )

    recalled = store.recall(principal_id="alice", task_id="task-1")
    assert len(recalled) == 1
    assert recalled[0].record_id == first.record_id
    assert recalled[0].content == "observed result"
    assert recalled[0].untrusted is True
    assert store.recall(principal_id="alice", task_id="other-task") == []


def test_checkpoint_round_trip_is_scope_isolated(tmp_path):
    store = SQLiteEpisodicMemory(tmp_path / "episodes.sqlite3")
    store.save_checkpoint(
        principal_id="alice",
        task_id="task-1",
        state={"step": 2, "episode_ids": ["e1"]},
    )

    assert store.load_checkpoint(principal_id="alice", task_id="task-1") == {
        "step": 2,
        "episode_ids": ["e1"],
    }
    assert store.load_checkpoint(principal_id="alice", task_id="task-2") is None


def test_rejects_oversized_and_invalid_scopes(tmp_path):
    store = SQLiteEpisodicMemory(tmp_path / "episodes.sqlite3", max_record_chars=4)
    with pytest.raises(ValueError):
        store.append(
            principal_id="alice",
            task_id="task-1",
            content="12345",
            source="test",
        )
    with pytest.raises(ValueError):
        store.recall(principal_id="", task_id="task-1")
