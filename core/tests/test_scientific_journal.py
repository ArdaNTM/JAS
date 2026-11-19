"""#11/#76: actual SQLite persistence, scoped notes and tamper rejection."""
from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest

from aura_core.memory.hierarchical_memory import SQLiteEpisodicMemory
from aura_core.research.scientific_journal import ScientificJournal


def make(path, *, principal="owner", task="experiment-1"):
    store = SQLiteEpisodicMemory(path)
    return ScientificJournal(store=store, principal_id=principal, task_id=task)


def add(journal, *, text="A negative result was observed",
        doi="10.1234/lab-notes", kind="negative_result",
        principal="owner", task="experiment-1", confirm=True):
    return journal.append_reviewed(
        principal_id=principal, task_id=task, kind=kind, text=text,
        source_doi=doi, confirm_local_persist=confirm,
    )


def test_real_sqlite_persistent_roundtrip_and_untrusted_provenance(tmp_path):
    path = tmp_path / "science.sqlite3"
    initial = make(path)
    stored = add(initial, text="Çalışma sonucu negatif")
    assert stored.persisted
    assert stored.untrusted
    assert not stored.publisher_verified
    assert not stored.owner_approval_verified
    assert not stored.authorization_checked
    assert not stored.encrypted_at_rest
    reloaded = make(path)
    entries = reloaded.recall(principal_id="owner", task_id="experiment-1")
    assert len(entries) == 1
    assert entries[0] == stored
    assert entries[0].source_doi == "10.1234/lab-notes"
    assert len(entries[0].data_sha256) == 64


def test_exact_principal_and_task_scope_isolation(tmp_path):
    path = tmp_path / "science.sqlite3"
    owner = make(path)
    add(owner, text="Owner secret")
    other = make(path, principal="another-owner")
    assert other.recall(principal_id="another-owner", task_id="experiment-1") == ()
    other_task = make(path, task="experiment-2")
    assert other_task.recall(principal_id="owner", task_id="experiment-2") == ()
    with pytest.raises(PermissionError):
        owner.recall(principal_id="another-owner", task_id="experiment-1")
    with pytest.raises(PermissionError):
        add(owner, principal="another-owner")


def test_explicit_confirmation_is_required_not_owner_receipt(tmp_path):
    journal = make(tmp_path / "science.sqlite3")
    for bad in (False, 1, "yes", None):
        with pytest.raises(PermissionError):
            add(journal, confirm=bad)
    assert journal.recall(principal_id="owner", task_id="experiment-1") == ()


@pytest.mark.parametrize("bad", [
    {"kind": "grant-root"},
    {"doi": "javascript:bad"},
    {"doi": "../secret"},
    {"text": ""},
    {"text": "\x00"},
    {"text": "X" * 1001},
    {"text": "\ud800"},
])
def test_bad_scientific_note_never_persists(tmp_path, bad):
    journal = make(tmp_path / "science.sqlite3")
    with pytest.raises(ValueError):
        add(journal, **bad)
    assert journal.recall(principal_id="owner", task_id="experiment-1") == ()


def test_excludes_non_scientific_records_in_same_memory_scope(tmp_path):
    store = SQLiteEpisodicMemory(tmp_path / "mixed.sqlite3")
    journal = ScientificJournal(store=store, principal_id="owner", task_id="experiment-1")
    store.append(
        principal_id="owner", task_id="experiment-1",
        content="An unrelated chat memory", source="chat",
    )
    add(journal)
    entries = journal.recall(principal_id="owner", task_id="experiment-1")
    assert len(entries) == 1
    assert "unrelated" not in repr(entries)


def test_tampered_persisted_record_rejected_on_recall(tmp_path):
    path = tmp_path / "science.sqlite3"
    journal = make(path)
    record = add(journal, text="Measured result")
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE episodic_records SET content = ? WHERE record_id = ?",
            ("Changed research text", record.record_id),
        )
    with pytest.raises(ValueError, match="digest mismatch"):
        journal.recall(principal_id="owner", task_id="experiment-1")


def test_malformed_scope_and_recall_limit_rejected(tmp_path):
    path = tmp_path / "science.sqlite3"
    with pytest.raises(ValueError):
        make(path, principal="../other")
    journal = make(path)
    with pytest.raises(ValueError):
        journal.recall(principal_id="owner", task_id="experiment-1", limit=True)
    with pytest.raises(ValueError):
        journal.recall(principal_id="owner", task_id="experiment-1", limit=51)
