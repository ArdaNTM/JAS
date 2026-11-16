"""Local SQLite visual memory with distinct scoped Core permissions.

Stores *descriptions and hashes only*, never raw pixels. The image description
must first pass an independently consented, registered vision MCP Gateway tool.
Core storage operations use the existing PermissionEngine; no MCP provider
execution occurs in the storage path. Owner auth and disk encryption remain
trusted deployment responsibilities, never inferred from caller arguments.
"""
from __future__ import annotations

import asyncio
import os
import re
import sqlite3
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import UUID, uuid4

from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType,
)
from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationRequest, PermissionEngine, RiskLevel,
)
from aura_core.kernel.services import (
    ServiceCategory, ServiceDefinition, ServiceRegistry,
)
from aura_core.providers.ollama_vision_mcp import (
    GovernedImageUnderstanding, ImageUnderstandingEvidence, _validate_identity,
)

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SCOPE = "memory/visual/"
_MAX_RECORDS = 500


class VisualMemoryDenied(PermissionError):
    """Explicit per-principal, per-operation permission is missing."""


class VisualMemoryUnavailable(RuntimeError):
    """Private local SQLite persistence is not available."""


@dataclass(frozen=True, slots=True)
class VisualMemoryReceipt:
    memory_id: str
    created_at: str
    image_sha256: str
    already_present: bool = False


@dataclass(frozen=True, slots=True)
class VisualMemoryRecord:
    memory_id: str
    description: str
    image_sha256: str
    provider_id: str
    created_at: str
    trust: str = "UNTRUSTED_VISUAL_MEMORY"


def _safe_text(
    value: str, *, limit: int, allow_empty: bool = False,
    allow_multiline: bool = False,
) -> str:
    if (
        not isinstance(value, str) or len(value) > limit
        or (not allow_empty and not value.strip())
        or any((ord(c) < 32 and not (allow_multiline and c in "\n\t")) or ord(c) == 127
               or 0xD800 <= ord(c) <= 0xDFFF for c in value)
    ):
        raise ValueError("Invalid bounded visual memory text")
    return value


class SQLiteVisualMemoryStore:
    """Real local SQLite database. Trusted composition supplies a private path."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path) or not path.is_absolute():
            raise ValueError("Visual memory database requires trusted absolute Path")
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError("Visual memory store path may not be a symlink")
        if not path.parent.is_dir():
            raise ValueError("Owner-private visual memory directory must already exist")
        self.path = path
        # Create with restrictive permissions before SQLite opens the database.
        if not path.exists():
            flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                fd = os.open(path, flags, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
        if path.is_symlink() or not path.is_file():
            raise ValueError("Visual memory must be a regular nonsymlink database")
        if os.name == "posix":
            mode = stat.S_IMODE(path.stat().st_mode)
            if mode & 0o077:
                raise ValueError("Private visual memory database must not be group/world-accessible")
        try:
            with self._connect() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS visual_records(
                        memory_id TEXT PRIMARY KEY,
                        principal_id TEXT NOT NULL,
                        image_sha256 TEXT NOT NULL,
                        description TEXT NOT NULL,
                        provider_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(principal_id, image_sha256)
                    )""")
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_visual_owner_recent
                    ON visual_records(principal_id, created_at DESC, memory_id DESC)""")
        except (sqlite3.Error, OSError) as exc:
            raise VisualMemoryUnavailable("Private visual memory database init failed") from exc

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=5)
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA secure_delete=ON")
        return connection

    def insert(self, *, principal: str, evidence: ImageUnderstandingEvidence) -> VisualMemoryReceipt:
        # This method is internal, never accepts arbitrary app principal from a client.
        ident = str(uuid4())
        when = datetime.now(timezone.utc).isoformat()
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute(
                    "SELECT memory_id,created_at FROM visual_records WHERE principal_id=? AND image_sha256=?",
                    (principal, evidence.image_sha256),
                ).fetchone()
                if existing:
                    return VisualMemoryReceipt(existing[0], existing[1], evidence.image_sha256, True)
                count = conn.execute(
                    "SELECT COUNT(*) FROM visual_records WHERE principal_id=?", (principal,),
                ).fetchone()[0]
                if count >= _MAX_RECORDS:
                    raise VisualMemoryUnavailable("Private visual memory quota exceeded")
                conn.execute(
                    "INSERT INTO visual_records(memory_id,principal_id,image_sha256,description,provider_id,created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (ident, principal, evidence.image_sha256, evidence.description,
                     evidence.provider_id, when),
                )
            return VisualMemoryReceipt(ident, when, evidence.image_sha256)
        except (sqlite3.Error, OSError) as exc:
            raise VisualMemoryUnavailable("Private visual memory write failed") from exc

    def list(self, *, principal: str, query: str, limit: int) -> tuple[VisualMemoryRecord, ...]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT memory_id,description,image_sha256,provider_id,created_at "
                    "FROM visual_records WHERE principal_id=? "
                    "AND instr(lower(description),lower(?))>0 "
                    "ORDER BY created_at DESC,memory_id DESC LIMIT ?",
                    (principal, query, limit),
                ).fetchall()
        except (sqlite3.Error, OSError) as exc:
            raise VisualMemoryUnavailable("Private visual memory read failed") from exc
        return tuple(VisualMemoryRecord(*row) for row in rows)

    def delete(self, *, principal: str, memory_id: str) -> bool:
        try:
            with self._connect() as conn:
                result = conn.execute(
                    "DELETE FROM visual_records WHERE principal_id=? AND memory_id=?",
                    (principal, memory_id),
                )
            return result.rowcount == 1
        except (sqlite3.Error, OSError) as exc:
            raise VisualMemoryUnavailable("Private visual memory delete failed") from exc


def register_visual_memory_capabilities(
    *, store: SQLiteVisualMemoryStore,
    services: ServiceRegistry,
    capabilities: CapabilityRegistry,
) -> None:
    """Opt-in existing Core registry integration. No policy is granted."""
    if not isinstance(store, SQLiteVisualMemoryStore):
        raise TypeError("Existing local SQLite visual memory required")
    if not isinstance(services, ServiceRegistry) or not isinstance(capabilities, CapabilityRegistry):
        raise TypeError("Authoritative Core registries are required")
    names = ("memory.visual.read", "memory.visual.write", "memory.visual.delete")
    if any(capabilities.providers(cap) for cap in names):
        raise ValueError("Visual memory capability already registered")
    service = services.register(ServiceDefinition(
        name="aura-private-visual-memory", version="1.0.0", provider="aura",
        category=ServiceCategory.CORE, capabilities=frozenset(names),
    ), store)
    for name in names:
        capabilities.register(CapabilityDefinition(
            capability_id=name, name=name, version="1.0.0",
            description="Explicitly authorized private visual SQLite metadata",
            provider_id=service.service_id, provider_type=ProviderType.SERVICE,
            category=CapabilityCategory.MEMORY,
            risk_level="medium" if name.endswith("read") else "high",
        ))


class GovernedVisualMemory:
    """Principal-bound model and SQLite operations; no raw pixels stored."""

    def __init__(
        self, store: SQLiteVisualMemoryStore, engine: PermissionEngine,
        vision: GovernedImageUnderstanding, *,
        authenticated_principal_id: str, event_bus: EventBus | None = None,
    ) -> None:
        if not isinstance(store, SQLiteVisualMemoryStore) or not isinstance(engine, PermissionEngine):
            raise TypeError("Existing SQLite store and PermissionEngine required")
        principal = _validate_identity(authenticated_principal_id)
        if (
            not isinstance(vision, GovernedImageUnderstanding)
            or vision._principal != principal
            or vision._gateway._permission_engine is not engine
        ):
            raise VisualMemoryDenied("Visual memory and model must share authenticated identity/policy engine")
        if event_bus is not None and not isinstance(event_bus, EventBus):
            raise TypeError("Existing Core EventBus required")
        self._store = store
        self._engine = engine
        self._vision = vision
        self._principal = principal
        self._scope = _SCOPE + quote(principal, safe="")
        self._events = event_bus

    def _authorize(self, operation: str, risk: RiskLevel) -> None:
        try:
            decision = self._engine.authorize(AuthorizationRequest(
                request_id="visual-memory:" + str(uuid4()),
                principal_id=self._principal, capability_id=operation,
                operation_id=operation, resource_scope=self._scope, risk_level=risk,
            ))
        except Exception as exc:
            raise VisualMemoryDenied("Visual memory policy unavailable") from exc
        if decision.decision is not AuthorizationDecision.ALLOW:
            raise VisualMemoryDenied("Explicit scoped visual memory permission required")

    async def remember_image(
        self, image: bytes, *, question: str = "Describe visible objects.",
        capture_confirmed: bool,
    ) -> VisualMemoryReceipt:
        if capture_confirmed is not True:
            raise VisualMemoryDenied("Explicit image consent required before visual memory")
        _safe_text(question, limit=500)
        # Deny before model inference if the caller cannot write its result.
        self._authorize("memory.visual.write", RiskLevel.HIGH)
        evidence = await self._vision.describe(
            image, prompt=question, capture_confirmed=True,
        )
        if (
            evidence.trust != "UNTRUSTED_LOCAL_MODEL_OUTPUT"
            or evidence.provider_id != "vision.ollama.local"
            or not _HEX.fullmatch(evidence.image_sha256)
        ):
            raise VisualMemoryUnavailable("Untrusted image evidence cannot be stored")
        _safe_text(evidence.description, limit=4000, allow_multiline=True)
        # Re-evaluate after the await to catch revocations in flight.
        self._authorize("memory.visual.write", RiskLevel.HIGH)
        receipt = await asyncio.to_thread(
            self._store.insert, principal=self._principal, evidence=evidence,
        )
        if self._events is not None:
            self._events.publish(KernelEvent(
                event_type="VisualMemoryRecordStored",
                source_component="aura.visual_memory",
                payload={"metadata_only": True, "already_present": receipt.already_present},
            ))
        return receipt

    def recall(
        self, *, query: str = "", limit: int = 10,
    ) -> tuple[VisualMemoryRecord, ...]:
        _safe_text(query, limit=200, allow_empty=True)
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Visual memory read limit must be 1..20")
        self._authorize("memory.visual.read", RiskLevel.MEDIUM)
        return self._store.list(principal=self._principal, query=query, limit=limit)

    def forget(self, *, memory_id: str) -> bool:
        if not isinstance(memory_id, str):
            raise ValueError("Invalid visual memory UUID")
        try:
            if str(UUID(memory_id)) != memory_id:
                raise ValueError("Noncanonical visual memory UUID")
        except (ValueError, AttributeError) as exc:
            raise ValueError("Invalid visual memory UUID") from exc
        self._authorize("memory.visual.delete", RiskLevel.HIGH)
        erased = self._store.delete(principal=self._principal, memory_id=memory_id)
        if erased and self._events is not None:
            self._events.publish(KernelEvent(
                event_type="VisualMemoryRecordDeleted",
                source_component="aura.visual_memory",
                payload={"metadata_only": True},
            ))
        return erased
