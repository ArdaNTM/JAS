"""Real SQLite offline archives require authorized fetch + explicit consent."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from aura_core.kernel.permissions import AuthorizationDecision
from aura_core.research.archive import SQLiteResearchArchive


def response(*, decision=AuthorizationDecision.ALLOW, content="Untrusted source body",
             status_code=200, content_type="text/plain"):
    return SimpleNamespace(decision=decision, result={
        "url": "https://example.org/report", "status_code": status_code,
        "content_type": content_type, "content": content,
    })


def test_archive_persists_authorized_result_with_exact_principal_isolation(tmp_path):
    path = tmp_path / "research.db"
    archive = SQLiteResearchArchive(path)
    payload = response()
    with pytest.raises(PermissionError):
        archive.archive_fetch_result(principal_id="alice", response=payload)
    entry = archive.archive_fetch_result(principal_id="alice", response=payload, consented=True)
    same = archive.archive_fetch_result(principal_id="alice", response=payload, consented=True)
    assert entry == same
    assert archive.get(principal_id="bob", archive_id=entry["archive_id"]) is None
    reopened = SQLiteResearchArchive(path)
    result = reopened.get(principal_id="alice", archive_id=entry["archive_id"])
    assert result is not None
    assert result["content"] == "Untrusted source body"
    assert result["untrusted"] and result["verified_source"] is False


def test_denied_and_invalid_fetches_fail_closed(tmp_path):
    archive = SQLiteResearchArchive(tmp_path / "research.db")
    with pytest.raises(PermissionError):
        archive.archive_fetch_result(
            principal_id="owner",
            response=response(decision=AuthorizationDecision.DENY),
            consented=True,
        )
    with pytest.raises(ValueError):
        archive.archive_fetch_result(
            principal_id="owner", response=response(status_code=500), consented=True,
        )
    with pytest.raises(ValueError):
        archive.archive_fetch_result(
            principal_id="owner", response=response(content_type="application/octet-stream"),
            consented=True,
        )
    with pytest.raises(ValueError):
        archive.archive_fetch_result(
            principal_id="owner", response=response(content=""), consented=True,
        )


def test_archive_does_not_parse_unstructured_mcp_text(tmp_path):
    archive = SQLiteResearchArchive(tmp_path / "research.db")
    fake = SimpleNamespace(
        decision=AuthorizationDecision.ALLOW,
        result=SimpleNamespace(
            isError=False, content=[SimpleNamespace(text='{"url":"https://example.org"}')],
            structuredContent=None,
        )
    )
    with pytest.raises(ValueError):
        archive.archive_fetch_result(principal_id="owner", response=fake, consented=True)


def test_explicit_forget_is_principal_scoped(tmp_path):
    archive = SQLiteResearchArchive(tmp_path / "research.db")
    entry = archive.archive_fetch_result(
        principal_id="owner", response=response(), consented=True,
    )
    key = entry["archive_id"]
    with pytest.raises(PermissionError):
        archive.forget(principal_id="owner", archive_id=key)
    assert not archive.forget(principal_id="other", archive_id=key, confirmed=True)
    assert archive.get(principal_id="owner", archive_id=key) is not None
    assert archive.forget(principal_id="owner", archive_id=key, confirmed=True)
    assert not archive.forget(principal_id="owner", archive_id=key, confirmed=True)
    assert archive.get(principal_id="owner", archive_id=key) is None


@pytest.mark.parametrize("principal", ["", " ", "bad\nprincipal"])
def test_bad_principal_fails_before_storage(tmp_path, principal):
    archive = SQLiteResearchArchive(tmp_path / "research.db")
    with pytest.raises(ValueError):
        archive.archive_fetch_result(
            principal_id=principal, response=response(), consented=True,
        )


def test_archive_detects_changed_content_without_returning_it(tmp_path):
    import sqlite3
    path = tmp_path / "research.db"
    archive = SQLiteResearchArchive(path)
    item = archive.archive_fetch_result(
        principal_id="owner", response=response(), consented=True,
    )
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE research_snapshots SET content='tampered' WHERE archive_id=?",
            (item["archive_id"],),
        )
    with pytest.raises(ValueError, match="integrity mismatch"):
        archive.get(principal_id="owner", archive_id=item["archive_id"])


def test_archive_content_limit_is_enforced(tmp_path):
    archive = SQLiteResearchArchive(tmp_path / "research.db", max_chars=4)
    with pytest.raises(ValueError, match="limit"):
        archive.archive_fetch_result(
            principal_id="owner", response=response(content="12345"),
            consented=True,
        )
