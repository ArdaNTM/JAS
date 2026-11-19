"""Subsystem pack 1: bounded maintenance, remote handoff, local development.

This module has no independent tool authority. Any GUI or code execution crosses
an already registered MCPGateway capability and its real approval lifecycle.
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import hmac
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Protocol


_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_NONCE = re.compile(r"[a-f0-9]{32,64}\Z")
_SIGNATURE = re.compile(r"[a-f0-9]{64}\Z")
_ACTIONS = frozenset({"observe", "click", "type", "key"})


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or _NAME.fullmatch(value) is None:
        raise ValueError(f"invalid {field}")
    return value


@contextmanager
def _database(path: Path):
    connection = sqlite3.connect(path, timeout=10.0, isolation_level=None)
    try:
        connection.execute("PRAGMA busy_timeout=10000")
        yield connection
    finally:
        connection.close()


class TelemetryProbe(Protocol):
    def snapshot(self) -> Mapping[str, Any]: ...


class MaintenanceAutomation:
    """Durable, bounded, read-only health observations; never mutates the host."""

    def __init__(self, db_path: str | Path, telemetry: TelemetryProbe | None = None) -> None:
        if telemetry is None:
            from aura_core.application.system_telemetry import SystemTelemetry
            telemetry = SystemTelemetry()

        self.path = Path(db_path)
        if not self.path.parent.is_dir():
            raise ValueError("maintenance database parent must already exist")
        self.telemetry = telemetry
        with _database(self.path) as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS maintenance_checks (
                job_id TEXT PRIMARY KEY, due_at INTEGER NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('pending','running','done','failed')),
                result TEXT, updated_at INTEGER NOT NULL
            )""")

    def schedule(self, job_id: str, due_at: datetime) -> None:
        _identifier(job_id, "job_id")
        if not isinstance(due_at, datetime) or due_at.tzinfo is None:
            raise ValueError("due_at must have an explicit timezone")
        epoch = int(due_at.astimezone(UTC).timestamp())
        if epoch < 0:
            raise ValueError("due_at must be nonnegative")
        with _database(self.path) as connection:
            connection.execute("INSERT INTO maintenance_checks VALUES (?,?,'pending',NULL,?)",
                               (job_id, epoch, int(time.time())))

    def run_due(self, *, now: int | None = None, limit: int = 8) -> list[dict[str, Any]]:
        if type(limit) is not int or not 1 <= limit <= 32:
            raise ValueError("invalid batch limit")
        timestamp = int(time.time()) if now is None else now
        if type(timestamp) is not int or timestamp < 0:
            raise ValueError("invalid timestamp")
        # Claim atomically; a competing worker cannot run the same health check.
        with _database(self.path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            pending = connection.execute(
                "SELECT job_id FROM maintenance_checks WHERE state='pending' AND due_at<=? "
                "ORDER BY due_at,job_id LIMIT ?", (timestamp, limit)
            ).fetchall()
            for (job_id,) in pending:
                connection.execute(
                    "UPDATE maintenance_checks SET state='running',updated_at=? WHERE job_id=?",
                    (timestamp, job_id),
                )
            connection.execute("COMMIT")
        reports: list[dict[str, Any]] = []
        for (job_id,) in pending:
            try:
                snapshot = dict(self.telemetry.snapshot())
                # Bounded evidence; no diagnostics command execution or self-healing.
                selected = {key: snapshot.get(key) for key in
                            ("status", "cpu_percent", "memory_percent", "alerts")}
                payload = json.dumps(selected, ensure_ascii=False, allow_nan=False)
                if len(payload.encode("utf-8")) > 16_384:
                    raise ValueError("oversized telemetry evidence")
                state = "done" if snapshot.get("status") == "ok" else "failed"
            except Exception:
                payload, state = '{"status":"telemetry_failed"}', "failed"
            with _database(self.path) as connection:
                connection.execute("UPDATE maintenance_checks SET state=?,result=?,updated_at=? "
                                   "WHERE job_id=? AND state='running'",
                                   (state, payload, timestamp, job_id))
            reports.append({"job_id": job_id, "state": state, "evidence": json.loads(payload)})
        return reports

    async def serve(self, stop: asyncio.Event, *, poll_seconds: float = 30.0) -> None:
        if not 0.1 <= poll_seconds <= 3600:
            raise ValueError("invalid poll interval")
        while not stop.is_set():
            await asyncio.to_thread(self.run_due)
            try:
                await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
            except TimeoutError:
                pass

    def status(self, job_id: str) -> dict[str, Any] | None:
        _identifier(job_id, "job_id")
        with _database(self.path) as connection:
            row = connection.execute("SELECT due_at,state,result FROM maintenance_checks WHERE job_id=?",
                                     (job_id,)).fetchone()
        return None if row is None else {
            "job_id": job_id, "due_at": row[0], "state": row[1],
            "evidence": json.loads(row[2]) if row[2] else None,
        }


class RemoteControlPrecondition:
    """Authenticated device handoff with a persistent, one-time nonce ledger.

    The HMAC key is locally provisioned, never received as a remote request
    field. This verifies transport provenance, NOT Owner approval. Gateway alone
    decides whether a ScreenControl operation may execute.
    """

    def __init__(self, *, gateway: Any, db_path: str | Path,
                 device_id: str, principal_id: str, key: bytes,
                 resource_scope: str = "local_default") -> None:
        self.gateway = gateway
        self.path = Path(db_path)
        self.device_id = _identifier(device_id, "device_id")
        self.principal_id = _identifier(principal_id, "principal_id")
        self.resource_scope = _identifier(resource_scope, "resource_scope")
        if type(key) is not bytes or len(key) < 32:
            raise ValueError("device HMAC key must contain at least 32 bytes")
        if not self.path.parent.is_dir():
            raise ValueError("nonce database parent must already exist")
        self._key = key
        with _database(self.path) as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS remote_nonces (
                device_id TEXT NOT NULL, nonce TEXT NOT NULL, expires_at INTEGER NOT NULL,
                PRIMARY KEY(device_id,nonce)
            )""")

    def fingerprint(self, envelope: Mapping[str, Any]) -> str:
        payload = json.dumps(envelope, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("ascii")
        if len(payload) > 8192:
            raise ValueError("oversized remote envelope")
        return hmac.new(self._key, payload, hashlib.sha256).hexdigest()

    async def forward(self, envelope: Mapping[str, Any], signature: str) -> Any:
        from aura_core.kernel.permissions import RiskLevel
        from aura_core.mcp.gateway import MCPGatewayRequest

        if not isinstance(envelope, dict) or set(envelope) != {
            "device_id", "principal_id", "nonce", "expires_at", "action", "approval_id"
        }:
            raise PermissionError("invalid remote request schema")
        if envelope["device_id"] != self.device_id or envelope["principal_id"] != self.principal_id:
            raise PermissionError("device/principal mismatch")
        if type(envelope["expires_at"]) is not int or not 0 <= envelope["expires_at"] - int(time.time()) <= 60:
            raise PermissionError("remote envelope expired or excessive lifetime")
        nonce = envelope["nonce"]
        if not isinstance(nonce, str) or _NONCE.fullmatch(nonce) is None:
            raise PermissionError("invalid replay nonce")
        action = envelope["action"]
        if not isinstance(action, dict) or action.get("action") not in _ACTIONS:
            raise PermissionError("unrecognized remote GUI action")
        if not set(action).issubset({"action", "x", "y", "text", "key"}):
            raise PermissionError("extra GUI arguments")
        approval_id = envelope["approval_id"]
        if approval_id is not None:
            _identifier(approval_id, "approval_id")
        if not isinstance(signature, str) or _SIGNATURE.fullmatch(signature) is None or not hmac.compare_digest(
            self.fingerprint(envelope), signature
        ):
            raise PermissionError("invalid remote device signature")
        # Persist the nonce before any potentially executing authorization call.
        try:
            with _database(self.path) as connection:
                connection.execute("INSERT INTO remote_nonces VALUES (?,?,?)",
                                   (self.device_id, nonce, envelope["expires_at"]))
        except sqlite3.IntegrityError as exc:
            raise PermissionError("replayed remote request") from exc
        return await self.gateway.invoke(MCPGatewayRequest(
            request_id=f"remote-{self.device_id}-{nonce}", principal_id=self.principal_id,
            capability_id="ScreenControl", operation_id="ScreenControl",
            resource_scope=self.resource_scope, risk_level=RiskLevel.HIGH,
            tool_name="screen_control", arguments=action, approval_id=approval_id,
        ))


@dataclass(frozen=True, slots=True)
class DevelopmentProposal:
    source: str
    tests: str
    digest: str


class LocalDevelopmentPlanner:
    """Uses real Ollama-compatible JSON inference; output is untrusted data."""

    def __init__(self, completion_provider: Any | None = None) -> None:
        if completion_provider is None:
            from aura_core.application.ollama_completion import OllamaJSONCompletionProvider
            completion_provider = OllamaJSONCompletionProvider()
        self.provider = completion_provider

    async def propose(self, requirement: str) -> DevelopmentProposal:
        if not isinstance(requirement, str) or not 1 <= len(requirement) <= 8000:
            raise ValueError("invalid requirement length")
        response = await self.provider.complete_json(
            system_prompt=("Return a JSON object with two Python strings: source and tests. "
                           "Include deterministic assertions. No tools are available. "
                           "Never claim execution or authorization."),
            user_prompt=requirement,
        )
        source, tests = response.get("source"), response.get("tests")
        if not isinstance(source, str) or not isinstance(tests, str) or not source.strip() or not tests.strip():
            raise ValueError("missing generated code or tests")
        if len(source.encode()) > 32000 or len(tests.encode()) > 16000:
            raise ValueError("generated draft exceeds sandbox input limits")
        ast.parse(source)
        ast.parse(tests)
        digest = hashlib.sha256((source + "\0" + tests).encode()).hexdigest()
        return DevelopmentProposal(source, tests, digest)


class ApprovedSandboxDispatcher:
    """Routes experiment execution to the existing, approval-only CodeAct MCP."""

    def __init__(self, gateway: Any, *, principal_id: str,
                 resource_scope: str = "local_default") -> None:
        self.gateway = gateway
        self.principal_id = _identifier(principal_id, "principal_id")
        self.resource_scope = _identifier(resource_scope, "resource_scope")

    async def execute(self, *, job_id: str, proposal: DevelopmentProposal,
                      approval_id: str | None) -> Any:
        from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
        from aura_core.mcp.gateway import MCPGatewayRequest

        _identifier(job_id, "job_id")
        if approval_id is not None:
            _identifier(approval_id, "approval_id")
        if not isinstance(proposal, DevelopmentProposal):
            raise ValueError("invalid development proposal")
        if hashlib.sha256((proposal.source + "\0" + proposal.tests).encode()).hexdigest() != proposal.digest:
            raise ValueError("proposal digest mismatch")
        # Both strings run only inside CodeAct's digest-pinned Docker container.
        script = ("namespace = {}\n" +
                  "exec(compile(" + repr(proposal.source) + ", '<draft>', 'exec'), namespace)\n" +
                  "exec(compile(" + repr(proposal.tests) + ", '<tests>', 'exec'), namespace)\n")
        if len(script.encode()) > 63_000:
            raise ValueError("sandbox payload exceeds configured limit")
        response = await self.gateway.invoke(MCPGatewayRequest(
            request_id=f"dev-{job_id}", principal_id=self.principal_id,
            capability_id="sandbox.codeact.execute", operation_id="sandbox.codeact.execute",
            resource_scope=self.resource_scope, risk_level=RiskLevel.HIGH,
            tool_name="codeact_execute", approval_id=approval_id,
            arguments={"job_id": job_id, "source": script, "input": {}},
        ))
        if response.decision is not AuthorizationDecision.ALLOW:
            raise PermissionError("CodeAct sandbox Gateway authorization not granted")
        return response.result
