import asyncio

import pytest

import aura_core.security.ws_ticket as ws_ticket_module
from aura_core.application.tasks import AgentTaskService, SubmittedTask
from aura_core.agent.runtime import Task
from aura_core.security.ws_ticket import WebSocketTicketManager


def test_ticket_is_one_time_and_rejects_expired_ticket(monkeypatch):
    clock = {"now": 1000}
    monkeypatch.setattr(ws_ticket_module.time, "time", lambda: clock["now"])

    manager = WebSocketTicketManager(secret="x" * 32, ttl_seconds=5)
    ticket = manager.issue()

    assert manager.verify(ticket.value) is True
    assert manager.verify(ticket.value) is False

    expired_ticket = manager.issue()
    clock["now"] = expired_ticket.expires_at

    assert manager.verify(expired_ticket.value) is False


def test_issue_prunes_expired_used_tickets(monkeypatch):
    clock = {"now": 2000}
    monkeypatch.setattr(ws_ticket_module.time, "time", lambda: clock["now"])

    manager = WebSocketTicketManager(secret="y" * 32, ttl_seconds=5)
    old_ticket = manager.issue()

    assert manager.verify(old_ticket.value) is True
    assert old_ticket.value in manager._used

    clock["now"] = old_ticket.expires_at
    manager.issue()

    assert old_ticket.value not in manager._used


class FakeRuntime:
    async def execute(self, task, plan):
        return object()


def test_task_result_requires_matching_principal():
    service = AgentTaskService(FakeRuntime())
    task = Task(
        task_id="ownership-test-001",
        principal_id="alice",
        title="Ownership test",
        resource_scope="local_default",
    )

    result = asyncio.run(
        service.submit(SubmittedTask(task=task, plan=None))
    )

    assert service.get_for_owner(task.task_id, "alice") is result

    with pytest.raises(KeyError):
        service.get_for_owner(task.task_id, "bob")

    with pytest.raises(KeyError):
        service.get_for_owner("missing-task", "alice")