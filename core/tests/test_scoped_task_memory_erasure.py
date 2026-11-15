"""Scoped task memory erasure: explicit confirmation, isolation and cleanup."""
from __future__ import annotations

import sqlite3

import pytest

from aura_core.memory.hierarchical_memory import SQLiteEpisodicMemory
from aura_core.application.task_memory import TaskMemoryCoordinator


def test_erasure_requires_explicit_confirmed_true(tmp_path):
    store = SQLiteEpisodicMemory(tmp_path / "memory.sqlite")
    store.append(principal_id="owner", task_id="task", content="private", source="test")
    store.save_checkpoint(principal_id="owner", task_id="task", state={"content": "private"})
    for bad in (False, 1, None, "yes"):
        with pytest.raises(PermissionError):
            store.forget_task(principal_id="owner", task_id="task", confirmed=bad)
    assert len(store.recall(principal_id="owner", task_id="task")) == 1
    assert store.load_checkpoint(principal_id="owner", task_id="task") is not None


def test_erasure_is_atomic_idempotent_and_principal_task_scoped(tmp_path):
    path = tmp_path / "memory.sqlite"
    store = SQLiteEpisodicMemory(path)
    for principal, task in (("owner", "task"), ("other", "task"), ("owner", "else")):
        store.append(principal_id=principal, task_id=task, content="secret", source="test")
        store.save_checkpoint(principal_id=principal, task_id=task, state={"secret": "private"})
    assert store.forget_task(principal_id="owner", task_id="task", confirmed=True) == (1, 1)
    assert store.forget_task(principal_id="owner", task_id="task", confirmed=True) == (0, 0)
    assert store.recall(principal_id="owner", task_id="task") == []
    assert store.load_checkpoint(principal_id="owner", task_id="task") is None
    for principal, task in (("other", "task"), ("owner", "else")):
        assert len(store.recall(principal_id=principal, task_id=task)) == 1
        assert store.load_checkpoint(principal_id=principal, task_id=task) is not None
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM episodic_records").fetchone()[0] == 2


def test_coordinator_evicts_only_matching_in_memory_scope(tmp_path):
    coordinator = TaskMemoryCoordinator(SQLiteEpisodicMemory(tmp_path / "memory.sqlite"))
    coordinator.begin(principal_id="owner", task_id="task", goal="private")
    coordinator.begin(principal_id="other", task_id="task", goal="other")
    assert ("owner", "task") in coordinator._contexts
    assert coordinator.forget_task(principal_id="owner", task_id="task", confirmed=True) == (1, 1)
    assert ("owner", "task") not in coordinator._contexts
    assert ("other", "task") in coordinator._contexts
    assert coordinator.store.recall(principal_id="owner", task_id="task") == []
    assert coordinator.store.load_checkpoint(principal_id="owner", task_id="task") is None
    assert len(coordinator.store.recall(principal_id="other", task_id="task")) == 1


@pytest.mark.parametrize("principal,task", [
    ("", "task"), ("owner", ""), ("owner\nnext", "task"),
    ("owner", "task\rnext"), (" ", "task")
])
def test_bad_scopes_fail_before_mutation(tmp_path, principal, task):
    store = SQLiteEpisodicMemory(tmp_path / "memory.sqlite")
    store.append(principal_id="owner", task_id="task", content="preserve", source="test")
    with pytest.raises(ValueError):
        store.forget_task(principal_id=principal, task_id=task, confirmed=True)
    assert len(store.recall(principal_id="owner", task_id="task")) == 1
