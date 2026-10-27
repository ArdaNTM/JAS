"""Bounded execution, redacted audit events, and provider circuit breaking.

These are reusable primitives, not a claim that AURA's complete runtime is
already wired through them. The audit ledger is in-memory; production use
requires a durable, access-controlled sink and external integrity anchoring.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Awaitable, Callable, TypeVar
from uuid import uuid4

T = TypeVar("T")


class BudgetExceeded(RuntimeError):
    """Raised when an execution exceeds its configured budget."""


@dataclass(slots=True)
class ExecutionBudget:
    """Per-task step/call budget with an optional monotonic deadline."""

    max_steps: int = 32
    max_tool_calls: int = 16
    deadline_monotonic: float | None = None
    steps_used: int = 0
    tool_calls_used: int = 0

    def __post_init__(self) -> None:
        if self.max_steps < 0 or self.max_tool_calls < 0:
            raise ValueError("Execution limits cannot be negative")

    def check(self, *, cancelled: bool = False) -> None:
        if cancelled:
            raise asyncio.CancelledError("Execution cancellation requested")
        if self.deadline_monotonic is not None and time.monotonic() >= self.deadline_monotonic:
            raise BudgetExceeded("Execution deadline exceeded")
        if self.steps_used > self.max_steps:
            raise BudgetExceeded("Execution step budget exceeded")
        if self.tool_calls_used > self.max_tool_calls:
            raise BudgetExceeded("Tool-call budget exceeded")

    def consume_step(self, *, cancelled: bool = False) -> None:
        self.check(cancelled=cancelled)
        if self.steps_used >= self.max_steps:
            raise BudgetExceeded("Execution step budget exceeded")
        self.steps_used += 1

    def consume_tool_call(self, *, cancelled: bool = False) -> None:
        self.check(cancelled=cancelled)
        if self.tool_calls_used >= self.max_tool_calls:
            raise BudgetExceeded("Tool-call budget exceeded")
        self.tool_calls_used += 1


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """Allowlisted audit metadata; arguments and provider output are excluded."""

    sequence: int
    event_id: str
    timestamp: str
    principal_id: str
    action: str
    resource_scope: str
    outcome: str
    reason_code: str
    previous_hash: str
    record_hash: str


class HashChainAuditLedger:
    """Thread-safe in-memory hash chain that stores metadata, never payloads.

    append intentionally accepts only scalar metadata fields. Do not pass tool
    arguments, prompts, credentials, transcripts, or provider responses.
    This class is a testable integrity primitive, not durable/WORM storage.
    """

    _GENESIS = "0" * 64

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []
        self._lock = threading.Lock()

    @staticmethod
    def _required(value: str, field_name: str, max_length: int = 256) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} is required")
        value = value.strip()
        if len(value) > max_length:
            raise ValueError(f"{field_name} exceeds its length limit")
        if any(ord(ch) < 32 for ch in value):
            raise ValueError(f"{field_name} contains control characters")
        return value

    @staticmethod
    def _digest(fields: dict[str, object]) -> str:
        encoded = json.dumps(
            fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def append(
        self, *, principal_id: str, action: str, resource_scope: str,
        outcome: str, reason_code: str,
    ) -> AuditRecord:
        principal_id = self._required(principal_id, "principal_id")
        action = self._required(action, "action")
        resource_scope = self._required(resource_scope, "resource_scope")
        outcome = self._required(outcome, "outcome", 64)
        reason_code = self._required(reason_code, "reason_code", 128)
        with self._lock:
            previous_hash = self._records[-1].record_hash if self._records else self._GENESIS
            fields: dict[str, object] = {
                "sequence": len(self._records) + 1,
                "event_id": str(uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "principal_id": principal_id,
                "action": action,
                "resource_scope": resource_scope,
                "outcome": outcome,
                "reason_code": reason_code,
                "previous_hash": previous_hash,
            }
            record = AuditRecord(**fields, record_hash=self._digest(fields))
            self._records.append(record)
            return record

    def snapshot(self) -> tuple[AuditRecord, ...]:
        with self._lock:
            return tuple(self._records)

    def verify(self) -> bool:
        with self._lock:
            previous_hash = self._GENESIS
            for index, record in enumerate(self._records, start=1):
                fields = {
                    "sequence": record.sequence,
                    "event_id": record.event_id,
                    "timestamp": record.timestamp,
                    "principal_id": record.principal_id,
                    "action": record.action,
                    "resource_scope": record.resource_scope,
                    "outcome": record.outcome,
                    "reason_code": record.reason_code,
                    "previous_hash": record.previous_hash,
                }
                if record.sequence != index or record.previous_hash != previous_hash:
                    return False
                if self._digest(fields) != record.record_hash:
                    return False
                previous_hash = record.record_hash
            return True


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when a provider circuit is open and calls are rejected."""


@dataclass(slots=True)
class CircuitBreaker:
    """Async circuit breaker with one half-open probe at a time."""

    failure_threshold: int = 3
    recovery_seconds: float = 30.0
    timeout_seconds: float | None = None
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failures: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)
    _probe_active: bool = field(default=False, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be positive")
        if self.recovery_seconds < 0:
            raise ValueError("recovery_seconds cannot be negative")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    @property
    def state(self) -> CircuitState:
        return self._state

    async def call(self, operation: Callable[[], Awaitable[T]]) -> T:
        async with self._lock:
            if self._state is CircuitState.OPEN:
                assert self._opened_at is not None
                if time.monotonic() - self._opened_at < self.recovery_seconds:
                    raise CircuitOpenError("Provider circuit is open")
                self._state = CircuitState.HALF_OPEN
            if self._state is CircuitState.HALF_OPEN:
                if self._probe_active:
                    raise CircuitOpenError("Provider recovery probe already in progress")
                self._probe_active = True

        try:
            result = (
                await asyncio.wait_for(operation(), timeout=self.timeout_seconds)
                if self.timeout_seconds is not None
                else await operation()
            )
        except asyncio.CancelledError:
            async with self._lock:
                if self._state is CircuitState.HALF_OPEN:
                    self._probe_active = False
            raise
        except Exception:
            async with self._lock:
                self._failures += 1
                if self._state is CircuitState.HALF_OPEN or self._failures >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    self._opened_at = time.monotonic()
                self._probe_active = False
            raise
        else:
            async with self._lock:
                self._failures = 0
                self._state = CircuitState.CLOSED
                self._opened_at = None
                self._probe_active = False
            return result
