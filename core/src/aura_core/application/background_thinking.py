"""Opt-in, bounded idle reflection over scoped episodic memories.

The worker only proposes possible links between existing records. It never edits
source memories, calls an LLM/provider, changes permissions, or executes tools.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Callable, Any

logger = logging.getLogger(__name__)


def _concepts(text: str) -> set[str]:
    tokens = re.findall(r"[\wğüşöçıİĞÜŞÖÇ]{4,}", text.casefold())
    stop = {"hakkında", "olarak", "içinde", "sonra", "önce", "lütfen", "bunu", "şunu", "yapmak", "yapıyor"}
    return {token for token in tokens if token not in stop and not token.isdigit()}


def propose_memory_links(records: list[Any], *, max_pairs: int = 5) -> list[dict[str, Any]]:
    """Create reviewable candidate links using bounded lexical overlap."""
    bounded = records[:20]
    proposals: list[dict[str, Any]] = []
    for left_index, left in enumerate(bounded):
        left_concepts = _concepts(str(getattr(left, "content", ""))[:1200])
        if len(left_concepts) < 2:
            continue
        for right in bounded[left_index + 1:]:
            if getattr(left, "memory_id", None) == getattr(right, "memory_id", None):
                continue
            overlap = sorted(left_concepts & _concepts(str(getattr(right, "content", ""))[:1200]))
            if len(overlap) < 2:
                continue
            proposals.append({
                "kind": "possible_memory_link",
                "source_memory_id": str(getattr(left, "memory_id", "")),
                "target_memory_id": str(getattr(right, "memory_id", "")),
                "shared_concepts": overlap[:8],
                "confidence": round(min(0.9, 0.35 + 0.1 * len(overlap)), 2),
                "review_required": True,
                "execution_performed": False,
            })
            if len(proposals) >= max(1, min(max_pairs, 5)):
                return proposals
    return proposals



def propose_memory_consolidation(records: list[Any], *, max_proposals: int = 5) -> list[dict[str, Any]]:
    """Derive review-only lessons from repeated patterns and possible contradictions.

    This deterministic first pass prefers explainable heuristics over pretending
    lexical overlap is semantic certainty. Every proposal cites source IDs and
    remains untrusted until a human reviews it.
    """
    bounded = records[:20]
    proposals: list[dict[str, Any]] = []
    contradiction_pairs = (
        ({"always", "never"}, "absolute_claim_conflict"),
        ({"works", "fails"}, "outcome_conflict"),
        ({"success", "failure"}, "outcome_conflict"),
        ({"enabled", "disabled"}, "state_conflict"),
        ({"true", "false"}, "state_conflict"),
        ({"çalışıyor", "çalışmıyor"}, "outcome_conflict"),
        ({"başarılı", "başarısız"}, "outcome_conflict"),
        ({"açık", "kapalı"}, "state_conflict"),
    )
    for i, left in enumerate(bounded):
        left_text = str(getattr(left, "content", ""))[:1200]
        left_tokens = _concepts(left_text)
        if not left_tokens:
            continue
        for right in bounded[i + 1:]:
            right_text = str(getattr(right, "content", ""))[:1200]
            right_tokens = _concepts(right_text)
            shared = sorted(left_tokens & right_tokens)
            if len(shared) < 2:
                continue
            left_id = str(getattr(left, "memory_id", getattr(left, "record_id", "")))
            right_id = str(getattr(right, "memory_id", getattr(right, "record_id", "")))
            if not left_id or not right_id or left_id == right_id:
                continue
            left_words = set(re.findall(r"[\wğüşöçıİĞÜŞÖÇ]+", left_text.casefold()))
            right_words = set(re.findall(r"[\wğüşöçıİĞÜŞÖÇ]+", right_text.casefold()))
            conflict = None
            for terms, kind in contradiction_pairs:
                left_hit = bool(terms & left_words)
                right_hit = bool(terms & right_words)
                if left_hit and right_hit and (terms & left_words) != (terms & right_words):
                    conflict = kind
                    break
            if conflict:
                proposals.append({
                    "kind": "possible_memory_contradiction",
                    "evidence_memory_ids": [left_id, right_id],
                    "shared_concepts": shared[:8],
                    "conflict_type": conflict,
                    "summary": "Two records may disagree; inspect context and timestamps before resolving.",
                    "confidence": 0.45,
                    "review_required": True,
                    "untrusted": True,
                    "execution_performed": False,
                })
            elif len(shared) >= 3:
                proposals.append({
                    "kind": "possible_repeated_lesson",
                    "evidence_memory_ids": [left_id, right_id],
                    "shared_concepts": shared[:8],
                    "summary": "Repeated evidence may support a reusable lesson; verify context and counterexamples.",
                    "confidence": round(min(0.7, 0.3 + 0.05 * len(shared)), 2),
                    "review_required": True,
                    "untrusted": True,
                    "execution_performed": False,
                })
            if len(proposals) >= max(1, min(int(max_proposals), 5)):
                return proposals
    return proposals


class IdleMemoryReflectionDaemon:
    """Runs only when explicitly enabled and the app has been idle long enough."""

    def __init__(
        self,
        *,
        memory_store: Any,
        principal_id: str,
        database_path: str | Path,
        idle_seconds: int = 300,
        interval_seconds: int = 900,
        last_activity: Callable[[], float] = time.monotonic,
    ) -> None:
        self.memory_store = memory_store
        self.principal_id = principal_id.strip()[:128]
        self.database_path = Path(database_path).expanduser()
        self.idle_seconds = max(60, min(int(idle_seconds), 86400))
        self.interval_seconds = max(60, min(int(interval_seconds), 86400))
        self.last_activity = last_activity
        self._task: asyncio.Task[None] | None = None
        self._cycles = 0
        self._proposals = 0
        self._errors = 0
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.database_path), timeout=5.0) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS reflection_proposals (
                proposal_id TEXT PRIMARY KEY,
                principal_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                reviewed INTEGER NOT NULL DEFAULT 0
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_reflection_scope ON reflection_proposals(principal_id, reviewed, created_at DESC)")

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="aura-idle-memory-reflection")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self._task is not None and not self._task.done(),
            "idle_seconds": self.idle_seconds,
            "interval_seconds": self.interval_seconds,
            "cycles": self._cycles,
            "proposals": self._proposals,
            "errors": self._errors,
            "mode": "reviewable_suggestions_only",
        }

    def list_proposals(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with sqlite3.connect(str(self.database_path), timeout=5.0) as db:
            rows = db.execute(
                "SELECT payload_json FROM reflection_proposals WHERE principal_id = ? AND reviewed = 0 ORDER BY created_at DESC LIMIT ?",
                (self.principal_id, max(1, min(int(limit), 50))),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    async def run_once(self) -> int:
        if not self.principal_id or time.monotonic() - self.last_activity() < self.idle_seconds:
            return 0
        records = await asyncio.to_thread(
            self.memory_store.recall,
            principal_id=self.principal_id,
            query="",
            limit=20,
        )
        proposals = propose_memory_links(records, max_pairs=5) + propose_memory_consolidation(records, max_proposals=5)
        now = time.time()
        saved = 0
        with sqlite3.connect(str(self.database_path), timeout=5.0) as db:
            for proposal in proposals:
                payload = dict(proposal)
                # Stable identity includes proposal kind and evidence IDs, preventing
                # duplicate proposals every idle cycle without merging unlike claims.
                import hashlib
                evidence = payload.get("evidence_memory_ids") or [
                    payload.get("source_memory_id", ""), payload.get("target_memory_id", "")
                ]
                identity = json.dumps(
                    [payload.get("kind", "unknown"), sorted(str(item) for item in evidence),
                     payload.get("conflict_type", ""), payload.get("shared_concepts", [])],
                    ensure_ascii=False, sort_keys=True,
                )
                proposal_id = hashlib.sha256((self.principal_id + "|" + identity).encode()).hexdigest()
                payload["proposal_id"] = proposal_id
                cursor = db.execute(
                    "INSERT OR IGNORE INTO reflection_proposals(proposal_id, principal_id, payload_json, created_at) VALUES (?, ?, ?, ?)",
                    (proposal_id, self.principal_id, json.dumps(payload, ensure_ascii=False), now),
                )
                saved += max(0, cursor.rowcount)
        self._cycles += 1
        self._proposals += saved
        return saved

    async def _run(self) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                self._errors += 1
                logger.warning("Idle memory reflection cycle failed", exc_info=True)
            await asyncio.sleep(self.interval_seconds)
