import pytest

from aura_core.enterprise.workflow_store import (
    InvalidWorkflowTransition,
    SQLiteWorkflowStore,
    WorkflowConflict,
    WorkflowStatus,
)


def test_workflow_store_creates_and_reuses_idempotent_request(tmp_path):
    database = str(tmp_path / "workflows.sqlite3")
    with SQLiteWorkflowStore(database) as store:
        first = store.create(
            workflow_id="wf-1", idempotency_key="idem-1",
            principal_id="local-user", task_id="task-1",
        )
        duplicate = store.create(
            workflow_id="wf-ignored", idempotency_key="idem-1",
            principal_id="local-user", task_id="task-1",
        )
        assert first == duplicate
        assert first.status is WorkflowStatus.PENDING
        assert first.version == 1
        assert store.get_by_idempotency_key("idem-1") == first


def test_workflow_store_rejects_idempotency_identity_conflict(tmp_path):
    with SQLiteWorkflowStore(str(tmp_path / "workflows.sqlite3")) as store:
        store.create(
            workflow_id="wf-1", idempotency_key="idem-1",
            principal_id="local-user", task_id="task-1",
        )
        with pytest.raises(WorkflowConflict):
            store.create(
                workflow_id="wf-2", idempotency_key="idem-1",
                principal_id="other-user", task_id="task-2",
            )


def test_workflow_transitions_use_optimistic_versions_and_terminal_states(tmp_path):
    with SQLiteWorkflowStore(str(tmp_path / "workflows.sqlite3")) as store:
        record = store.create(
            workflow_id="wf-1", idempotency_key="idem-1",
            principal_id="local-user", task_id="task-1",
        )
        running = store.transition(
            record.workflow_id, expected_version=1, target=WorkflowStatus.RUNNING,
        )
        assert running.version == 2
        with pytest.raises(WorkflowConflict):
            store.transition(
                record.workflow_id, expected_version=1, target=WorkflowStatus.FAILED,
            )
        succeeded = store.transition(
            record.workflow_id, expected_version=2, target=WorkflowStatus.SUCCEEDED,
        )
        assert succeeded.version == 3
        with pytest.raises(InvalidWorkflowTransition):
            store.transition(
                record.workflow_id, expected_version=3, target=WorkflowStatus.RUNNING,
            )


def test_checkpoint_is_opaque_versioned_and_only_saved_while_running(tmp_path):
    with SQLiteWorkflowStore(str(tmp_path / "workflows.sqlite3")) as store:
        record = store.create(
            workflow_id="wf-1", idempotency_key="idem-1",
            principal_id="local-user", task_id="task-1",
        )
        with pytest.raises(InvalidWorkflowTransition):
            store.save_checkpoint(
                record.workflow_id, expected_version=1, checkpoint_ref="checkpoint://wf-1/1",
            )
        running = store.transition(
            record.workflow_id, expected_version=1, target=WorkflowStatus.RUNNING,
        )
        checkpointed = store.save_checkpoint(
            record.workflow_id, expected_version=running.version,
            checkpoint_ref="checkpoint://wf-1/1",
        )
        assert checkpointed.checkpoint_ref == "checkpoint://wf-1/1"
        assert checkpointed.version == 3
        assert "arguments" not in checkpointed.__dataclass_fields__


def test_workflow_store_rejects_control_characters_and_invalid_versions(tmp_path):
    with SQLiteWorkflowStore(str(tmp_path / "workflows.sqlite3")) as store:
        with pytest.raises(ValueError):
            store.create(
                workflow_id="wf-1", idempotency_key="idem-1",
                principal_id="user\\nsecret", task_id="task-1",
            )
        record = store.create(
            workflow_id="wf-1", idempotency_key="idem-1",
            principal_id="local-user", task_id="task-1",
        )
        with pytest.raises(ValueError):
            store.transition(
                record.workflow_id, expected_version=0, target=WorkflowStatus.RUNNING,
            )
