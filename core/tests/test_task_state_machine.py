from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aura_core.application.task_state_machine import TaskState, TaskStateMachine
from aura_core.kernel.events import EventBus


def test_dependencies_gate_ready_state_and_emit_progress_events(tmp_path) -> None:
    bus = EventBus()
    machine = TaskStateMachine(tmp_path / "tasks.sqlite3", event_bus=bus)
    parent = machine.create_task(principal_id="alice", task_id="parent", goal="research")
    child = machine.create_task(
        principal_id="alice", task_id="child", goal="summarize",
        dependencies=["parent"],
    )
    assert parent.state == TaskState.READY
    assert child.state == TaskState.PENDING

    machine.transition("parent", principal_id="alice", target=TaskState.RUNNING)
    machine.transition(
        "parent", principal_id="alice", target=TaskState.SUCCEEDED,
        result_summary="verified",
    )
    assert machine.get("child", principal_id="alice").state == TaskState.READY
    assert bus.snapshot()["published_total"] >= 5
    machine.close()


def test_failed_dependency_blocks_descendants(tmp_path) -> None:
    machine = TaskStateMachine(tmp_path / "tasks.sqlite3")
    machine.create_task(principal_id="alice", task_id="a", goal="first")
    machine.create_task(principal_id="alice", task_id="b", goal="second", dependencies=["a"])
    machine.create_task(principal_id="alice", task_id="c", goal="third", dependencies=["b"])
    machine.transition("a", principal_id="alice", target=TaskState.RUNNING)
    machine.transition("a", principal_id="alice", target=TaskState.FAILED, error="boom")
    assert machine.get("b", principal_id="alice").state == TaskState.BLOCKED
    assert machine.get("c", principal_id="alice").state == TaskState.BLOCKED
    machine.close()


def test_task_state_is_persistent_and_principal_scoped(tmp_path) -> None:
    path = tmp_path / "tasks.sqlite3"
    machine = TaskStateMachine(path)
    created = machine.create_task(principal_id="alice", task_id="persist", goal="remember")
    machine.close()

    reopened = TaskStateMachine(path)
    loaded = reopened.get("persist", principal_id="alice")
    assert loaded.state == created.state
    assert loaded.revision == created.revision
    with pytest.raises(KeyError):
        reopened.get("persist", principal_id="bob")
    reopened.close()


def test_invalid_transitions_and_cross_principal_dependencies_are_rejected(tmp_path) -> None:
    machine = TaskStateMachine(tmp_path / "tasks.sqlite3")
    machine.create_task(principal_id="alice", task_id="a", goal="private")
    machine.create_task(principal_id="bob", task_id="b", goal="other")
    with pytest.raises(ValueError, match="same principal"):
        machine.create_task(
            principal_id="alice", task_id="c", goal="cross-scope", dependencies=["b"]
        )
    with pytest.raises(ValueError, match="Invalid task transition"):
        machine.transition("a", principal_id="alice", target=TaskState.SUCCEEDED)
    machine.close()


def test_cancel_pending_and_request_cancel_running(tmp_path) -> None:
    machine = TaskStateMachine(tmp_path / "tasks.sqlite3")
    machine.create_task(principal_id="alice", task_id="pending", goal="cancel me")
    assert machine.request_cancel("pending", principal_id="alice").state == TaskState.CANCELLED

    machine.create_task(principal_id="alice", task_id="running", goal="stop safely")
    machine.transition("running", principal_id="alice", target=TaskState.RUNNING)
    requested = machine.request_cancel("running", principal_id="alice")
    assert requested.state == TaskState.RUNNING
    assert requested.cancellation_requested is True
    assert machine.transition(
        "running", principal_id="alice", target=TaskState.CANCELLED
    ).state == TaskState.CANCELLED
    machine.close()


def test_deadline_expiration_marks_task_timed_out(tmp_path) -> None:
    machine = TaskStateMachine(tmp_path / "tasks.sqlite3")
    created = machine.create_task(
        principal_id="alice", task_id="deadline", goal="time bound",
        timeout_seconds=60,
    )
    assert created.deadline is not None
    expired = machine.expire_timeouts(now=created.deadline + timedelta(seconds=1))
    assert [item.task_id for item in expired] == ["deadline"]
    assert machine.get("deadline", principal_id="alice").state == TaskState.TIMED_OUT
    assert machine.expire_timeouts(now=datetime.now(UTC) + timedelta(days=1)) == ()
    machine.close()


def test_unknown_dependencies_and_invalid_timeouts_are_rejected(tmp_path) -> None:
    machine = TaskStateMachine(tmp_path / "tasks.sqlite3")
    with pytest.raises(ValueError, match="Unknown dependency"):
        machine.create_task(
            principal_id="alice", task_id="child", goal="orphan", dependencies=["missing"]
        )
    with pytest.raises(ValueError, match="positive"):
        machine.create_task(
            principal_id="alice", task_id="bad-timeout", goal="invalid", timeout_seconds=0
        )
    machine.close()
