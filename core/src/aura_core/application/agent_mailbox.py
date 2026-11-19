"""Durable, scoped AURA specialist mailboxes and optional Gateway-only agent binding.

The SQLite store transports untrusted *data*, not commands. Agent identities
must be provisioned by trusted bootstrap; the real authenticated caller must
be validated at the HTTP/transport entrypoint before MCPGatewayRequest creation.
No permission policies or Owner credentials are created here.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import sqlite3
from datetime import UTC, datetime
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.kernel.capabilities import CapabilityCategory, CapabilityDefinition, ProviderType
from aura_core.kernel.services import ServiceCategory, ServiceDefinition
from aura_core.mcp.provider import ProviderDefinition

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_ROLES = frozenset({"coder", "researcher"})
_AGENT_TOOLS = {
    "agent_send": "aura.agent.mailbox.send",
    "agent_read": "aura.agent.mailbox.read",
    "agent_consume": "aura.agent.mailbox.consume",
}


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
    """Principal/task-keyed SQLite queue. A direct caller is NOT authenticated.

    Default :memory: is isolated and SQL-based. Supply a persisted path for
    process restarts. No network listener or background agent dispatcher.
    """

    def __init__(
        self, *, principal_id: str, task_id: str,
        max_pending: int = 128, database_path: str | Path = ":memory:",
    ) -> None:
        self._principal = self._validate_id(principal_id, "principal")
        self._task = self._validate_id(task_id, "task")
        if type(max_pending) is not int or not 1 <= max_pending <= 128:
            raise ValueError("max_pending must be 1..128")
        self.max_pending = max_pending
        path = str(database_path)
        if path != ":memory:":
            Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, isolation_level=None, timeout=5.0,
                                   check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA busy_timeout=5000")
        if path != ":memory:":
            self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("""CREATE TABLE IF NOT EXISTS agent_messages(
            principal_id TEXT NOT NULL, task_id TEXT NOT NULL,
            message_id TEXT NOT NULL, sender_role TEXT NOT NULL,
            recipient_role TEXT NOT NULL, sequence INTEGER NOT NULL,
            text TEXT NOT NULL,
            PRIMARY KEY (principal_id, task_id, message_id)
        )""")
        self._db.execute("""CREATE INDEX IF NOT EXISTS agent_message_order
            ON agent_messages(principal_id, task_id, recipient_role, sequence)""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS agent_seen(
            principal_id TEXT NOT NULL, task_id TEXT NOT NULL,
            message_id TEXT NOT NULL, sequence INTEGER NOT NULL,
            PRIMARY KEY(principal_id, task_id, message_id),
            UNIQUE(principal_id, task_id, sequence)
        )""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS agent_delivery_receipts(
            principal_id TEXT NOT NULL, task_id TEXT NOT NULL,
            message_id TEXT NOT NULL, receiver_principal TEXT NOT NULL,
            receipt_json TEXT NOT NULL, signature_hex TEXT NOT NULL,
            PRIMARY KEY(principal_id, task_id, message_id)
        )""")

    def close(self) -> None:
        with self._lock:
            self._db.close()

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

    @staticmethod
    def _record(row: sqlite3.Row) -> SpecialistMessage:
        return SpecialistMessage(
            message_id=row["message_id"], sender_role=row["sender_role"],
            recipient_role=row["recipient_role"], sequence=row["sequence"],
            text=row["text"],
        )

    def send(
        self, *, principal_id: str, task_id: str,
        message_id: str, sender_role: str, recipient_role: str,
        text: str,
    ) -> SpecialistMessage:
        """Store one bounded untrusted message, transactionally with replay ID."""
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
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                if self._db.execute(
                    "SELECT 1 FROM agent_seen WHERE principal_id=? AND task_id=? AND message_id=?",
                    (self._principal, self._task, identity),
                ).fetchone():
                    raise ValueError("duplicate specialist message id")
                nseen = self._db.execute(
                    "SELECT COUNT(*) FROM agent_seen WHERE principal_id=? AND task_id=?",
                    (self._principal, self._task),
                ).fetchone()[0]
                if nseen >= 1024:
                    raise OverflowError("specialist replay ledger is full")
                count = self._db.execute(
                    "SELECT COUNT(*) FROM agent_messages WHERE principal_id=? AND task_id=?",
                    (self._principal, self._task),
                ).fetchone()[0]
                if count >= self.max_pending:
                    raise OverflowError("specialist mailbox is full")
                seq = self._db.execute(
                    "SELECT COALESCE(MAX(sequence),0)+1 FROM agent_seen WHERE principal_id=? AND task_id=?",
                    (self._principal, self._task),
                ).fetchone()[0]
                self._db.execute("""INSERT INTO agent_seen
                    (principal_id, task_id, message_id, sequence) VALUES(?,?,?,?)""",
                    (self._principal, self._task, identity, seq))
                self._db.execute("""INSERT INTO agent_messages
                    (principal_id, task_id, message_id, sender_role,
                     recipient_role, sequence, text) VALUES(?,?,?,?,?,?,?)""",
                    (self._principal, self._task, identity, sender, recipient, seq, text))
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        return SpecialistMessage(identity, sender, recipient, seq, text)

    def inspect(
        self, *, principal_id: str, task_id: str,
        recipient_role: str, limit: int = 20,
    ) -> tuple[SpecialistMessage, ...]:
        """View pending data, never execute it or mark recipient as delivered."""
        self._scope(principal_id, task_id)
        role = self._role(recipient_role)
        if type(limit) is not int or not 1 <= limit <= 128:
            raise ValueError("invalid mailbox read limit")
        with self._lock:
            rows = self._db.execute("""SELECT * FROM agent_messages
                WHERE principal_id=? AND task_id=? AND recipient_role=?
                ORDER BY sequence LIMIT ?""",
                (self._principal, self._task, role, limit)).fetchall()
        return tuple(map(self._record, rows))

    def consume(
        self, *, principal_id: str, task_id: str,
        recipient_role: str, confirm: bool = False, limit: int = 20,
        receipt_signing_key: bytes | None = None,
        receiver_principal: str | None = None,
    ) -> tuple[SpecialistMessage, ...]:
        """Explicit data consumption only; caller confirmation != authorization."""
        self._scope(principal_id, task_id)
        role = self._role(recipient_role)
        if type(confirm) is not bool or not confirm:
            raise PermissionError("explicit mailbox consumption required")
        if type(limit) is not int or not 1 <= limit <= 128:
            raise ValueError("invalid mailbox read limit")
        if (receipt_signing_key is None) != (receiver_principal is None):
            raise PermissionError("receipt signer and authenticated receiver must be paired")
        if receipt_signing_key is not None:
            if type(receipt_signing_key) is not bytes or len(receipt_signing_key) < 32:
                raise PermissionError("receipt signing key requires >=32 bytes")
            receiver_principal = self._validate_id(receiver_principal, "receiver")
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                rows = self._db.execute("""SELECT * FROM agent_messages
                    WHERE principal_id=? AND task_id=? AND recipient_role=?
                    ORDER BY sequence LIMIT ?""",
                    (self._principal, self._task, role, limit)).fetchall()
                for row in rows:
                    self._db.execute("""DELETE FROM agent_messages
                        WHERE principal_id=? AND task_id=? AND message_id=?""",
                        (self._principal, self._task, row["message_id"]))
                    if receipt_signing_key is not None:
                        receipt = {
                            "schema": "aura.agent.delivery-receipt.v1",
                            "principal_id": self._principal, "task_id": self._task,
                            "message_id": row["message_id"], "sequence": row["sequence"],
                            "sender_role": row["sender_role"],
                            "recipient_role": row["recipient_role"],
                            "receiver_principal": receiver_principal,
                            "text_sha256": hashlib.sha256(row["text"].encode("utf-8")).hexdigest(),
                            "consumed_at": datetime.now(UTC).isoformat(),
                        }
                        payload = json.dumps(receipt, sort_keys=True,
                                             separators=(",", ":"), ensure_ascii=False)
                        mac = hmac.new(receipt_signing_key, payload.encode("utf-8"),
                                       hashlib.sha256).hexdigest()
                        self._db.execute("""INSERT INTO agent_delivery_receipts
                            (principal_id, task_id, message_id, receiver_principal,
                             receipt_json, signature_hex) VALUES(?,?,?,?,?,?)""",
                            (self._principal, self._task, row["message_id"],
                             receiver_principal, payload, mac))
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        # Durable seen ledger retained after consume; replay is still denied.
        return tuple(map(self._record, rows))


    def delivery_receipt(self, *, principal_id: str, task_id: str,
                         message_id: str, receiver_principal: str) -> dict | None:
        """Read durable signed consumption proof scoped to the attested receiver."""
        self._scope(principal_id, task_id)
        mid = self._validate_id(message_id, "message")
        principal = self._validate_id(receiver_principal, "receiver")
        with self._lock:
            row = self._db.execute("""SELECT receipt_json, signature_hex
                FROM agent_delivery_receipts WHERE principal_id=? AND task_id=?
                AND message_id=? AND receiver_principal=?""",
                (self._principal, self._task, mid, principal)).fetchone()
        if row is None:
            return None
        return {"receipt": json.loads(row["receipt_json"]),
                "signature_hex": row["signature_hex"]}

    @staticmethod
    def verify_delivery_receipt(record: dict, signing_key: bytes) -> bool:
        """Verify a broker-signed record; NOT an independent receiver signature."""
        if type(signing_key) is not bytes or len(signing_key) < 32:
            raise ValueError("trusted receipt verification key required")
        if type(record) is not dict or set(record) != {"receipt", "signature_hex"}:
            return False
        payload, sig = record["receipt"], record["signature_hex"]
        if (type(payload) is not dict or
                payload.get("schema") != "aura.agent.delivery-receipt.v1" or
                type(sig) is not str or len(sig) != 64 or
                any(c not in "0123456789abcdef" for c in sig)):
            return False
        try:
            raw = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, UnicodeError):
            return False
        expected = hmac.new(signing_key, raw, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig)

    def pending_count(self, *, principal_id: str, task_id: str) -> int:
        self._scope(principal_id, task_id)
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*) FROM agent_messages WHERE principal_id=? AND task_id=?",
                (self._principal, self._task)).fetchone()
        return int(row[0])


@dataclass(frozen=True, slots=True)
class AgentBinding:
    """Trusted bootstrap assignment, *not* user/model-supplied tool arguments."""
    agent_principal: str
    owner_principal: str
    task_id: str
    role: str

    def __post_init__(self):
        for field in ("agent_principal", "owner_principal", "task_id"):
            ScopedAgentMailbox._validate_id(getattr(self, field), field)
        ScopedAgentMailbox._role(self.role)


class GovernedAgentMailboxMCP:
    """Optional MCP-facing adapter: Gateway dispatch + trusted static role roster.

    The upstream entrypoint must authenticate caller principal ID. A caller may
    not assert a sender role or override the mailbox owner/task via arguments.
    """

    provider_id = "aura.governed-agent-mailbox"

    def __init__(self, mailbox: ScopedAgentMailbox,
                 bindings: Mapping[str, AgentBinding],
                 *, receipt_signing_key: bytes | None = None) -> None:
        if not isinstance(mailbox, ScopedAgentMailbox) or not bindings:
            raise ValueError("Existing SQLite mailbox and trusted roster required")
        if receipt_signing_key is not None and (
            type(receipt_signing_key) is not bytes or len(receipt_signing_key) < 32
        ):
            raise ValueError("independent broker receipt key must be >=32 bytes")
        self.mailbox = mailbox
        self._receipt_key = receipt_signing_key
        self._bindings = dict(bindings)
        for principal, binding in self._bindings.items():
            if principal != binding.agent_principal:
                raise ValueError("roster key and agent principal mismatch")
            if binding.owner_principal != mailbox._principal or binding.task_id != mailbox._task:
                raise ValueError("roster cannot cross mailbox task/owner scope")

    async def list_tools(self) -> tuple[MCPTool, ...]:
        return (
            MCPTool("agent_send", "Queue untrusted scoped message", {
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "minLength": 1, "maxLength": 128},
                    "recipient_role": {"type": "string", "enum": sorted(_ROLES)},
                    "text": {"type": "string", "minLength": 1, "maxLength": 2048},
                }, "required": ["message_id", "recipient_role", "text"],
                "additionalProperties": False,
            }),
            MCPTool("agent_read", "Read addressed pending untrusted messages", {
                "type": "object", "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 128}
                }, "additionalProperties": False,
            }),
            MCPTool("agent_consume", "Consume pending messages with single-use Owner approval", {
                "type": "object", "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 128}
                }, "additionalProperties": False,
            }),
        )

    async def call_tool(self, name: str, arguments: Any = None) -> dict[str, Any]:
        grant = current_dispatch()
        if (grant is None or name not in _AGENT_TOOLS or
            grant.capability_id != _AGENT_TOOLS[name] or grant.tool_name != name or
            grant.principal_id not in self._bindings):
            raise PermissionError("Verified Gateway grant and roster binding required")
        if name == "agent_consume" and (not grant.approval_consumed or
                                        grant.risk_level not in ("high", "critical")):
            raise PermissionError("Message consumption requires consumed HIGH approval")
        binding = self._bindings[grant.principal_id]
        from aura_core.mcp.gateway import _validate_json_schema
        tools = {tool.name: tool.input_schema for tool in await self.list_tools()}
        args = arguments if isinstance(arguments, dict) else {}
        _validate_json_schema(args, tools[name])
        owner, task = binding.owner_principal, binding.task_id
        if name == "agent_send":
            if args["recipient_role"] == binding.role:
                raise ValueError("self-send is not permitted")
            message = await asyncio.to_thread(self.mailbox.send,
                principal_id=owner, task_id=task, message_id=args["message_id"],
                sender_role=binding.role, recipient_role=args["recipient_role"],
                text=args["text"])
            return {"message_id": message.message_id, "sequence": message.sequence,
                    "queued": True, "delivered_to_agent": False,
                    "sender_roster_bound": True, "upstream_identity_attested": False}
        if name == "agent_read":
            result = await asyncio.to_thread(self.mailbox.inspect,
                principal_id=owner, task_id=task, recipient_role=binding.role,
                limit=args.get("limit", 20))
        else:
            result = await asyncio.to_thread(self.mailbox.consume,
                principal_id=owner, task_id=task, recipient_role=binding.role,
                confirm=True, limit=args.get("limit", 20),
                receipt_signing_key=self._receipt_key,
                receiver_principal=(grant.principal_id if self._receipt_key else None))
        response = {"messages": [
            {"message_id": item.message_id, "sequence": item.sequence,
             "sender_role": item.sender_role, "recipient_role": item.recipient_role,
             "text": item.text, "untrusted": True, "delivered_to_agent": False}
            for item in result
        ]}
        if name == "agent_consume" and self._receipt_key is not None:
            response["broker_signed_receipts"] = [
                self.mailbox.delivery_receipt(
                    principal_id=owner, task_id=task,
                    message_id=item.message_id,
                    receiver_principal=grant.principal_id)
                for item in result
            ]
        return response


def register_governed_agent_mailbox(kernel: Any, provider: GovernedAgentMailboxMCP) -> None:
    """Explicit registry enrollment ONLY; caller must install policies separately."""
    if (kernel.service_registry is None or kernel.provider_registry is None or
        kernel.capability_registry is None):
        raise RuntimeError("Kernel must be bootstrapped")
    service = ServiceDefinition(
        name="governed_agent_mailbox", version="1.0.0", provider="aura",
        category=ServiceCategory.MCP,
        capabilities=frozenset(_AGENT_TOOLS.values()),
    )
    kernel.service_registry.register(service, provider)
    kernel.provider_registry.register(ProviderDefinition(
        provider_id=provider.provider_id, name="Governed SQLite Specialist Mailbox",
        version="1.0.0", service_id=service.service_id), provider)
    for name, cap in _AGENT_TOOLS.items():
        kernel.capability_registry.register(CapabilityDefinition(
            capability_id=cap, name="Mailbox " + name, version="1.0.0",
            description="Trusted roster and scoped SQLite message data only",
            provider_id=provider.provider_id, provider_type=ProviderType.MCP,
            category=CapabilityCategory.AUTOMATION,
            tool_name=name, risk_level="high" if name == "agent_consume" else "low",
        ))
