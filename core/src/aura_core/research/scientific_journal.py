"""Reviewed offline science note persistence using JAS's existing SQLite memory.

The journal requires a preconfigured store, never accepts arbitrary paths or
creates a new MCP capability. Caller must independently authenticate,
authorize and obtain actual Owner consent before any durable data write.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from aura_core.memory.hierarchical_memory import SQLiteEpisodicMemory

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_DOI = re.compile(r"10\.[0-9]{4,9}/[a-z0-9._;()/:+-]{1,160}\Z", re.ASCII)
_KINDS = frozenset({"hypothesis", "observation", "negative_result", "literature_note"})
_SOURCE = "aura_science_local_review_v1"


@dataclass(frozen=True, slots=True)
class ScientificJournalEntry:
    record_id: str
    kind: str
    text: str
    source_doi: str
    data_sha256: str
    created_at: float
    untrusted: bool = True
    persisted: bool = True
    publisher_verified: bool = False
    owner_approval_verified: bool = False
    authorization_checked: bool = False
    encrypted_at_rest: bool = False


class ScientificJournal:
    """Exact-principal/task wrapper around existing JAS episodic persistence."""

    def __init__(
        self, *, store: SQLiteEpisodicMemory,
        principal_id: str, task_id: str,
    ) -> None:
        if type(store) is not SQLiteEpisodicMemory:
            raise ValueError("existing SQLiteEpisodicMemory store required")
        self.store = store
        self._principal = self._id(principal_id)
        self._task = self._id(task_id)

    @staticmethod
    def _id(value: str) -> str:
        if type(value) is not str or not _ID.fullmatch(value):
            raise ValueError("invalid exact journal identity")
        return value

    def _scope(self, principal_id: str, task_id: str) -> None:
        principal, task = self._id(principal_id), self._id(task_id)
        if principal != self._principal or task != self._task:
            raise PermissionError("journal scope mismatch")

    @staticmethod
    def _source_doi(value: str) -> str:
        if type(value) is not str:
            raise ValueError("source DOI must be literal text")
        normalized = value.casefold()
        if not _DOI.fullmatch(normalized):
            raise ValueError("invalid research DOI")
        return normalized

    @staticmethod
    def _text(value: str) -> str:
        if (
            type(value) is not str or not 1 <= len(value.strip()) <= 1000
            or "\x00" in value or "\r" in value
        ):
            raise ValueError("invalid research note")
        try:
            value.encode("utf-8")
        except UnicodeError as exc:
            raise ValueError("invalid research note Unicode") from exc
        return value.strip()

    def append_reviewed(
        self, *, principal_id: str, task_id: str, kind: str,
        text: str, source_doi: str, confirm_local_persist: bool = False,
    ) -> ScientificJournalEntry:
        """Write one untrusted note only after explicit local opt-in.

        Local boolean confirmation cannot substitute for a signed Owner
        receipt or authenticated MCP Gateway authorization.
        """
        self._scope(principal_id, task_id)
        if type(confirm_local_persist) is not bool or not confirm_local_persist:
            raise PermissionError("explicit local persistence confirmation required")
        if type(kind) is not str or kind not in _KINDS:
            raise ValueError("unsupported scientific observation kind")
        message = self._text(text)
        doi = self._source_doi(source_doi)
        fingerprint = hashlib.sha256(
            (kind + "\0" + doi + "\0" + message).encode("utf-8")
        ).hexdigest()
        record = self.store.append(
            principal_id=self._principal,
            task_id=self._task,
            content=message,
            source=_SOURCE,
            metadata={"kind": kind, "doi": doi, "data_sha256": fingerprint},
        )
        return ScientificJournalEntry(
            record_id=record.record_id, kind=kind, text=message,
            source_doi=doi, data_sha256=fingerprint,
            created_at=record.created_at,
        )

    def recall(
        self, *, principal_id: str, task_id: str, limit: int = 20,
    ) -> tuple[ScientificJournalEntry, ...]:
        """Retrieve scoped notes but never claim publisher or Owner authority."""
        self._scope(principal_id, task_id)
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("journal recall limit must be 1..50")
        # Other episodic records in the same scope may consume the store's
        # recall budget. Do not claim this is an exhaustive source index.
        records = self.store.recall(
            principal_id=self._principal, task_id=self._task,
            limit=min(100, max(limit, 50)),
        )
        output: list[ScientificJournalEntry] = []
        for record in records:
            if record.source != _SOURCE:
                continue
            metadata = record.metadata
            if not isinstance(metadata, dict):
                raise ValueError("invalid stored scientific metadata")
            kind = metadata.get("kind")
            doi = metadata.get("doi")
            fingerprint = metadata.get("data_sha256")
            if type(kind) is not str or kind not in _KINDS:
                raise ValueError("invalid stored scientific kind")
            normalized = self._source_doi(doi)
            message = self._text(record.content)
            expected = hashlib.sha256(
                (kind + "\0" + normalized + "\0" + message).encode("utf-8")
            ).hexdigest()
            if type(fingerprint) is not str or fingerprint != expected:
                raise ValueError("stored scientific note digest mismatch")
            output.append(ScientificJournalEntry(
                record_id=record.record_id,
                kind=kind, text=message, source_doi=normalized,
                data_sha256=expected, created_at=record.created_at,
            ))
            if len(output) >= limit:
                break
        return tuple(output)
