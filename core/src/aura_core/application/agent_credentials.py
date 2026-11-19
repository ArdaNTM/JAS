"""Authenticated, replay-protected agent-message ingress for the real MCPGateway.

HMAC keys must be provisioned separately by the Owner. This module never
changes PermissionEngine or supplies a policy, never accepts model-authored
principal/resource scope, and does not claim TPM/Windows Owner attestation.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from aura_core.application.agent_mailbox import (
    AgentBinding, GovernedAgentMailboxMCP, _AGENT_TOOLS,
)
from aura_core.kernel.permissions import RiskLevel
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest, MCPGatewayResponse

_NONCE = re.compile(r"[0-9a-f]{32,64}\Z", re.ASCII)
_SIG = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


def _payload_digest(name: str, arguments: dict[str, Any]) -> str:
    if name not in _AGENT_TOOLS or type(arguments) is not dict:
        raise ValueError("unsupported tool or argument envelope")
    try:
        encoded = json.dumps(arguments, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ValueError("invalid authenticated argument JSON") from exc
    if len(encoded) > 4096:
        raise ValueError("authenticated argument envelope too large")
    return hashlib.sha256(encoded).hexdigest()


def canonical_agent_auth_payload(
    principal_id: str, name: str, arguments: dict[str, Any],
    nonce: str, timestamp: int, approval_id: str | None = None,
) -> bytes:
    if not isinstance(principal_id, str) or not principal_id or "\n" in principal_id:
        raise ValueError("invalid authenticated principal")
    if type(timestamp) is not int or timestamp < 0:
        raise ValueError("invalid timestamp")
    if type(nonce) is not str or not _NONCE.fullmatch(nonce):
        raise ValueError("nonce must be 32..64 lowercase hex")
    digest = _payload_digest(name, arguments)
    if approval_id is not None and (type(approval_id) is not str or
                                    not 1 <= len(approval_id) <= 128):
        raise ValueError("invalid signed approval reference")
    return f"aura-agent-v1\n{principal_id}\n{name}\n{timestamp}\n{nonce}\n{digest}\n{approval_id or ''}".encode("utf-8")


@dataclass(frozen=True, slots=True)
class SignedAgentRequest:
    principal_id: str
    tool_name: str
    arguments: dict[str, Any]
    timestamp: int
    nonce: str
    signature_hex: str
    approval_id: str | None = None


class AuthenticatedAgentGateway:
    """Trusted principal→secret roster; atomic SQLite nonce and real Gateway call."""

    def __init__(
        self, gateway: MCPGateway, provider: GovernedAgentMailboxMCP,
        *, signing_keys: Mapping[str, bytes], nonce_database: str | Path,
        max_skew_seconds: int = 60,
    ) -> None:
        if not isinstance(gateway, MCPGateway) or not isinstance(provider, GovernedAgentMailboxMCP):
            raise TypeError("existing Gateway and governed mailbox provider required")
        if type(max_skew_seconds) is not int or not 10 <= max_skew_seconds <= 300:
            raise ValueError("bounded time skew required")
        self._gateway = gateway
        self._provider = provider
        self._skew = max_skew_seconds
        keys = dict(signing_keys)
        if set(keys) != set(provider._bindings):
            raise ValueError("exact roster keys required; no fallback or wildcards")
        if any(type(value) is not bytes or len(value) < 32 for value in keys.values()):
            raise ValueError("each agent requires independent >=32-byte HMAC key")
        self._keys = keys
        path = str(nonce_database)
        if path != ":memory:":
            Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, timeout=5.0, isolation_level=None,
                                   check_same_thread=False)
        self._db.execute("PRAGMA busy_timeout=5000")
        if path != ":memory:":
            self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("""CREATE TABLE IF NOT EXISTS agent_auth_nonces(
            principal_id TEXT NOT NULL,
            nonce TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            PRIMARY KEY(principal_id, nonce)
        )""")

    def close(self) -> None:
        with self._lock:
            self._db.close()

    async def invoke(self, request: SignedAgentRequest) -> MCPGatewayResponse:
        """Verify actual HMAC and nonce before constructing MCPGatewayRequest."""
        if type(request) is not SignedAgentRequest:
            raise PermissionError("signed agent request required")
        principal = request.principal_id
        if principal not in self._keys or type(request.signature_hex) is not str:
            raise PermissionError("unknown or unsigned agent")
        if not _SIG.fullmatch(request.signature_hex):
            raise PermissionError("malformed agent signature")
        try:
            material = canonical_agent_auth_payload(
                principal, request.tool_name, request.arguments,
                request.nonce, request.timestamp, request.approval_id,
            )
        except ValueError as exc:
            raise PermissionError("invalid agent signed envelope") from exc
        if abs(time.time() - request.timestamp) > self._skew:
            raise PermissionError("stale agent request")
        expected = hmac.new(self._keys[principal], material, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, request.signature_hex):
            raise PermissionError("agent identity signature rejected")
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                # Bounded durable replay ledger. No prune while accepted timestamps
                # remain in window; expiry is enforced before any DB write.
                nseen = self._db.execute(
                    "SELECT COUNT(*) FROM agent_auth_nonces WHERE principal_id=?",
                    (principal,),
                ).fetchone()[0]
                if nseen >= 10_000:
                    raise PermissionError("agent replay ledger capacity exceeded")
                self._db.execute(
                    "INSERT INTO agent_auth_nonces(principal_id,nonce,timestamp) VALUES(?,?,?)",
                    (principal, request.nonce, request.timestamp),
                )
                self._db.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                self._db.execute("ROLLBACK")
                raise PermissionError("replayed authenticated agent request") from exc
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        binding = self._provider._bindings[principal]
        cap = _AGENT_TOOLS[request.tool_name]
        scope = f"tasks/{binding.owner_principal}/{binding.task_id}"
        return await self._gateway.invoke(MCPGatewayRequest(
            request_id="agent-"+request.nonce,
            principal_id=principal, capability_id=cap, operation_id=cap,
            resource_scope=scope,
            risk_level=RiskLevel.HIGH if request.tool_name == "agent_consume" else RiskLevel.LOW,
            tool_name=request.tool_name, arguments=request.arguments,
            approval_id=request.approval_id,
        ))
