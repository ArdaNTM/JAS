"""Feature #5: existing task state machine supplies a read-only owner-scoped view."""
from __future__ import annotations

import pytest

from aura_core.application.task_state_machine import TaskState, TaskStateMachine


def test_projection_is_owner_scoped_and_reports_actual_state(tmp_path):
    manager = TaskStateMachine(tmp_path / "tasks.sqlite")
    try:
        first = manager.create_task(principal_id="owner", goal="One", task_id="a")
        manager.create_task(principal_id="other", goal="Private", task_id="secret")
        manager.create_task(principal_id="owner", goal="Two", task_id="b")
        manager.transition(first.task_id, principal_id="owner", target=TaskState.RUNNING)
        manager.transition(first.task_id, principal_id="owner", target=TaskState.SUCCEEDED)
        data = manager.status_projection(principal_id="owner")
        assert data["total"] == 2
        assert data["counts"]["succeeded"] == 1
        assert data["counts"]["ready"] == 1
        assert sum(data["counts"].values()) == 2
        assert {row["task_id"] for row in data["recent"]} == {"a", "b"}
        assert all(row["untrusted"] for row in data["recent"])
        assert all("secret" not in str(row) for row in data["recent"])
        assert data["authorization_checked"] is False
        other = manager.status_projection(principal_id="other")
        assert other["total"] == 1
        assert other["recent"][0]["task_id"] == "secret"
        assert manager.status_projection(principal_id="not-found")["total"] == 0
    finally:
        manager.close()


def test_projection_is_bounded_and_never_changes_revision(tmp_path):
    manager = TaskStateMachine(tmp_path / "tasks.sqlite")
    try:
        for i in range(30):
            manager.create_task(principal_id="owner", goal="Goal", task_id=f"t{i:02d}")
        before = {r.task_id: r.revision for r in manager.list_tasks(principal_id="owner")}
        snapshot = manager.status_projection(principal_id="owner", limit=5)
        after = {r.task_id: r.revision for r in manager.list_tasks(principal_id="owner")}
        assert snapshot["total"] == 30
        assert len(snapshot["recent"]) == 5
        assert before == after
        assert snapshot["read_only"] is True
    finally:
        manager.close()


@pytest.mark.parametrize("principal,limit", [
    ("", 1), (" ", 1), ("owner\nnext", 1), ("owner", 0),
    ("owner", 51), ("owner", True), ("owner", 2.5),
])
def test_bad_projection_scope_and_limit_rejected(tmp_path, principal, limit):
    manager = TaskStateMachine(tmp_path / "tasks.sqlite")
    try:
        with pytest.raises(ValueError):
            manager.status_projection(principal_id=principal, limit=limit)
    finally:
        manager.close()


def test_projection_unknown_principal_is_safe(tmp_path):
    manager = TaskStateMachine(tmp_path / "tasks.sqlite")
    try:
        manager.create_task(principal_id="alice", goal="Sensitive", task_id="a")
        data = manager.status_projection(principal_id="alice' OR 1=1 --")
        assert data["total"] == 0
        assert data["recent"] == []
        assert all(count == 0 for count in data["counts"].values())
    finally:
        manager.close()
