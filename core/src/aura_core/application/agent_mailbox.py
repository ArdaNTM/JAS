"""Bounded, synchronous data-only mailbox between existing specialist role labels.

No agents, tools, MCP invocations, Owner permissions or network channels are
created. Sender/recipient labels are unverified caller assertions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_ROLES = frozenset({"coder", "researcher"})


@dataclass(frozen=True, slots=True)
class SpecialistMessage:
    message_id: str
    sender_role: str
    recipient_role: str
    sequence: int
    text: str
    untrusted: bool = True
    sender_authenticated: bool = False
    authorization_checked: bool = False
    delivered_to_agent: bool = False
    tool_executed: bool = False


class ScopedAgentMailbox:
    """One owner/task-scoped ephemeral queue; no background consumer."""

    def __init__(
        self, *, principal_id: str, task_id: str,
        max_pending: int = 128,
    ) -> None:
        self._principal = self._validate_id(principal_id, "principal")
        self._task = self._validate_id(task_id, "task")
        if type(max_pending) is not int or not 1 <= max_pending <= 128:
            raise ValueError("max_pending must be 1..128")
        self.max_pending = max_pending
        self._messages: list[SpecialistMessage] = []
        self._seen_ids: set[str] = set()
        self._sequence = 0

    @staticmethod
    def _validate_id(value: str, label: str) -> str:
        if type(value) is not str or not _ID.fullmatch(value):
            raise ValueError(f"invalid {label} identity")
        return value

    @staticmethod
    def _role(value: str) -> str:
        if type(value) is not str or value not in _ROLES:
            raise ValueError("unsupported specialist role")
        return value

    def _scope(self, principal_id: str, task_id: str) -> None:
        principal = self._validate_id(principal_id, "principal")
        task = self._validate_id(task_id, "task")
        if principal != self._principal or task != self._task:
            raise PermissionError("specialist mailbox scope mismatch")

    def send(
        self, *, principal_id: str, task_id: str,
        message_id: str, sender_role: str, recipient_role: str,
        text: str,
    ) -> SpecialistMessage:
        """Queue an untrusted message for review; never dispatch a tool."""
        self._scope(principal_id, task_id)
        identity = self._validate_id(message_id, "message")
        sender = self._role(sender_role)
        recipient = self._role(recipient_role)
        if sender == recipient:
            raise ValueError("self-messaging is not supported")
        if (
            type(text) is not str or not 1 <= len(text.strip()) <= 2048
            or any(ord(char) in (0, 13) for char in text)
        ):
            raise ValueError("invalid specialist message")
        try:
            encoded = text.encode("utf-8")
        except UnicodeError as exc:
            raise ValueError("invalid message encoding") from exc
        if len(encoded) > 4096:
            raise ValueError("specialist message exceeds byte budget")
        if identity in self._seen_ids:
            raise ValueError("duplicate specialist message id")
        if len(self._messages) >= self.max_pending:
            raise OverflowError("specialist mailbox is full")
        if len(self._seen_ids) >= 1024:
            raise OverflowError("specialist replay ledger is full")
        record = SpecialistMessage(
            message_id=identity,
            sender_role=sender,
            recipient_role=recipient,
            sequence=self._sequence + 1,
            text=text,
        )
        self._sequence += 1
        self._seen_ids.add(identity)
        self._messages.append(record)
        return record

    def inspect(
        self, *, principal_id: str, task_id: str,
        recipient_role: str, limit: int = 20,
    ) -> tuple[SpecialistMessage, ...]:
        """Read only data addressed to the named role; does not deliver it."""
        self._scope(principal_id, task_id)
        role = self._role(recipient_role)
        if type(limit) is not int or not 1 <= limit <= 128:
            raise ValueError("invalid mailbox read limit")
        return tuple(
            record for record in self._messages if record.recipient_role == role
        )[:limit]

    def consume(
        self, *, principal_id: str, task_id: str,
        recipient_role: str, confirm: bool = False, limit: int = 20,
    ) -> tuple[SpecialistMessage, ...]:
        """Explicitly remove viewed data; confirmation is not authorization."""
        self._scope(principal_id, task_id)
        role = self._role(recipient_role)
        if type(confirm) is not bool or not confirm:
            raise PermissionError("explicit mailbox consumption required")
        viewed = self.inspect(
            principal_id=principal_id, task_id=task_id,
            recipient_role=role, limit=limit,
        )
        if viewed:
            ids = {record.message_id for record in viewed}
            self._messages = [
                record for record in self._messages
                if record.message_id not in ids
            ]
        return viewed

    def pending_count(self, *, principal_id: str, task_id: str) -> int:
        self._scope(principal_id, task_id)
        return len(self._messages)
