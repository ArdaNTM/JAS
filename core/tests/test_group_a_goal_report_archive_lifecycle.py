"""Focused real persistent Group A goal, sourced report and archive lifecycle tests."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from aura_core.application.task_state_machine import TaskState, TaskStateMachine
from aura_core.kernel.permissions import AuthorizationDecision
from aura_core.research.archive import SQLiteResearchArchive
from aura_core.research.citations import CitationReview
from aura_core.research.report_authoring import author_archived_research_report


def _result(body: str = "Archived scientific result") -> SimpleNamespace:
    return SimpleNamespace(
        decision=AuthorizationDecision.ALLOW,
        result={
            "url": "https://example.org/doi/10.1234/example",
            "status_code": 200,
            "content_type": "text/plain",
            "content": body,
        },
    )


def test_goal_progress_is_reopened_scoped_and_uses_actual_task_outcomes(tmp_path):
    path = tmp_path / "tasks.sqlite"
    machine = TaskStateMachine(path)
    machine.create_task(principal_id="owner", task_id="task-a", goal="build")
    machine.create_task(principal_id="owner", task_id="task-b", goal="build")
    machine.create_task(principal_id="other", task_id="task-c", goal="build")
    assert machine.goal_progress(principal_id="owner", goal="build")["percent_complete"] == 0
    machine.transition("task-a", principal_id="owner", target=TaskState.RUNNING)
    machine.transition("task-a", principal_id="owner", target=TaskState.SUCCEEDED)
    machine.close()
    reopened = TaskStateMachine(path)
    try:
        outcome = reopened.goal_progress(principal_id="owner", goal="build")
        assert (outcome["total"], outcome["succeeded"], outcome["percent_complete"]) == (2, 1, 50)
        assert outcome["completion_derived_from_db"] is True
        assert outcome["claimed_completion_verified"] is False
        assert reopened.goal_progress(principal_id="other", goal="build")["total"] == 1
        with pytest.raises(ValueError):
            reopened.goal_progress(principal_id="owner", goal="build", limit=1)
        with pytest.raises(ValueError):
            reopened.goal_progress(principal_id="owner", goal="build", limit=True)
    finally:
        reopened.close()


def test_archived_report_builds_real_docx_from_digest_checked_principal_data(tmp_path):
    store = SQLiteResearchArchive(tmp_path / "archive.sqlite")
    entry = store.archive_fetch_result(
        principal_id="owner", response=_result(), consented=True,
    )
    cite = CitationReview(
        doi="10.1234/example", title="Example", authors=("Researcher",),
        publication_year=2026, venue="Journal", source_ids=("known",),
        conflicting_metadata=False,
    )
    report = author_archived_research_report(
        archive=store, principal_id="owner", title="Evidence",
        sources=((entry["archive_id"], cite.doi),), citations=(cite,),
    )
    assert report.docx()[:2] == b"PK"
    assert entry["content_sha256"] in report.markdown()
    assert "Untrusted quotation:" in report.markdown()
    assert not report.source_authenticity_verified
    with pytest.raises(PermissionError):
        author_archived_research_report(
            archive=store, principal_id="other", title="cross-principal",
            sources=((entry["archive_id"], cite.doi),), citations=(cite,),
        )
    with pytest.raises(ValueError, match="reviewed"):
        author_archived_research_report(
            archive=store, principal_id="owner", title="unknown DOI",
            sources=((entry["archive_id"], "10.1234/other"),), citations=(cite,),
        )


def test_signed_archive_backup_restore_and_atomic_tamper_rejection(tmp_path):
    original = SQLiteResearchArchive(tmp_path / "original.sqlite")
    record = original.archive_fetch_result(
        principal_id="owner", response=_result("Evidence body"), consented=True)
    key = b"owner-provisioned-archive-backup-key-32bytes!"
    with pytest.raises(PermissionError):
        original.export_signed_backup(principal_id="owner", signing_key=key)
    backup = original.export_signed_backup(
        principal_id="owner", signing_key=key, confirmed=True)
    replica = SQLiteResearchArchive(tmp_path / "restored.sqlite")
    with pytest.raises(PermissionError):
        replica.restore_signed_backup(
            principal_id="other", backup=backup, signing_key=key, confirmed=True)
    with pytest.raises(PermissionError):
        replica.restore_signed_backup(
            principal_id="owner", backup=backup, signing_key=b"x"*32, confirmed=True)
    forged = json.loads(backup)
    forged["payload"]["records"][0]["content"] = "tampered"
    with pytest.raises(PermissionError):
        replica.restore_signed_backup(
            principal_id="owner", backup=json.dumps(forged).encode(),
            signing_key=key, confirmed=True)
    assert replica.get(principal_id="owner", archive_id=record["archive_id"]) is None
    assert replica.restore_signed_backup(
        principal_id="owner", backup=backup, signing_key=key, confirmed=True) == 1
    recovered = replica.get(principal_id="owner", archive_id=record["archive_id"])
    assert recovered["content"] == "Evidence body"
    assert recovered["content_sha256"] == record["content_sha256"]
