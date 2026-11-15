"""Feature #59: real in-process role messaging with strict exact-scope isolation."""
from __future__ import annotations

import pytest

from aura_core.application.agent_mailbox import ScopedAgentMailbox


def mailbox(*, max_pending=4):
    return ScopedAgentMailbox(
        principal_id="owner:1", task_id="task-42", max_pending=max_pending,
    )


def send(queue, *, sender="coder", recipient="researcher", mid="m1",
         principal="owner:1", task="task-42", text="Review this result"):
    return queue.send(
        principal_id=principal, task_id=task, message_id=mid,
        sender_role=sender, recipient_role=recipient, text=text,
    )


def test_data_only_message_sequence_and_recipient_selection():
    queue = mailbox()
    first = send(queue)
    second = send(queue, sender="researcher", recipient="coder", mid="m2")
    assert (first.sequence, second.sequence) == (1, 2)
    assert first.untrusted
    assert not first.sender_authenticated
    assert not first.authorization_checked
    assert not first.delivered_to_agent
    assert not first.tool_executed
    assert queue.inspect(
        principal_id="owner:1", task_id="task-42", recipient_role="coder"
    ) == (second,)
    assert queue.inspect(
        principal_id="owner:1", task_id="task-42", recipient_role="researcher"
    ) == (first,)


def test_cross_principal_or_task_access_is_denied_before_mutation():
    queue = mailbox()
    send(queue)
    with pytest.raises(PermissionError):
        send(queue, mid="m2", principal="other")
    with pytest.raises(PermissionError):
        queue.inspect(
            principal_id="owner:1", task_id="other", recipient_role="researcher"
        )
    with pytest.raises(PermissionError):
        queue.consume(
            principal_id="other", task_id="task-42",
            recipient_role="researcher", confirm=True,
        )
    assert queue.pending_count(principal_id="owner:1", task_id="task-42") == 1


def test_explicit_consumption_and_replay_rejection_after_removal():
    queue = mailbox()
    send(queue)
    with pytest.raises(PermissionError):
        queue.consume(
            principal_id="owner:1", task_id="task-42",
            recipient_role="researcher",
        )
    messages = queue.consume(
        principal_id="owner:1", task_id="task-42",
        recipient_role="researcher", confirm=True,
    )
    assert len(messages) == 1
    assert queue.pending_count(principal_id="owner:1", task_id="task-42") == 0
    with pytest.raises(ValueError, match="duplicate"):
        send(queue)


def test_bounded_queue_full_rejected_without_partial_append():
    queue = mailbox(max_pending=1)
    send(queue)
    with pytest.raises(OverflowError, match="full"):
        send(queue, mid="m2")
    assert queue.pending_count(principal_id="owner:1", task_id="task-42") == 1
    assert len(queue.inspect(
        principal_id="owner:1", task_id="task-42", recipient_role="researcher"
    )) == 1


@pytest.mark.parametrize("values", [
    {"sender": "root"},
    {"recipient": "operator"},
    {"sender": "coder", "recipient": "coder"},
    {"mid": "../escape"},
    {"text": ""},
    {"text": "\x00payload"},
    {"text": "x" * 2049},
    {"text": "€" * 1500},
    {"text": "\ud800"},
])
def test_invalid_role_identity_or_message_rejected(values):
    queue = mailbox()
    with pytest.raises(ValueError):
        send(queue, **values)
    assert queue.pending_count(principal_id="owner:1", task_id="task-42") == 0


def test_boolean_limits_and_confirm_are_not_authority():
    with pytest.raises(ValueError):
        mailbox(max_pending=True)
    queue = mailbox()
    send(queue)
    with pytest.raises(ValueError):
        queue.inspect(
            principal_id="owner:1", task_id="task-42",
            recipient_role="researcher", limit=True,
        )
    with pytest.raises(PermissionError):
        queue.consume(
            principal_id="owner:1", task_id="task-42",
            recipient_role="researcher", confirm=1,
        )
