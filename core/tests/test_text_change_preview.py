"""Feature #34/#52: transaction previews, stale-write denial and exact rollback."""
from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from aura_core.application.text_change_preview import (
    TextPatchRequest, preview_text_rollback, preview_text_transaction,
)


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def preview():
    original = {"src/app.py": "def greet():\n    return 'old'\n",
                "docs/notes.md": "Phase: one\n"}
    changes = (
        TextPatchRequest("src/app.py", digest(original["src/app.py"]), "'old'", "'new'"),
        TextPatchRequest("docs/notes.md", digest(original["docs/notes.md"]), "one", "two"),
    )
    return original, changes, preview_text_transaction(
        original, changes, principal_id="owner", task_id="t1",
    )


def test_real_multifile_preview_and_exact_rollback_are_deterministic():
    original, changes, result = preview()
    assert original["src/app.py"] == "def greet():\n    return 'old'\n"
    assert result.proposed_files[1][1].endswith("'new'\n")
    assert len(result.records) == 2
    assert result == preview_text_transaction(
        original, tuple(reversed(changes)), principal_id="owner", task_id="t1",
    )
    restored = preview_text_rollback(
        result, dict(result.proposed_files), principal_id="owner", task_id="t1",
    )
    assert restored == original
    assert not result.filesystem_changed
    assert not result.rollback_executed
    assert not result.authorization_checked
    assert result.untrusted_data
    assert len(result.transaction_fingerprint) == 64


def test_stale_revision_rejected_before_any_preview():
    files = {"src/a.txt": "hello"}
    with pytest.raises(ValueError, match="stale"):
        preview_text_transaction(
            files, (TextPatchRequest("src/a.txt", "0" * 64, "hello", "bye"),),
            principal_id="owner", task_id="t1",
        )
    assert files["src/a.txt"] == "hello"


def test_rollback_rejects_external_change_to_proposed_bytes():
    _, _, result = preview()
    changed = dict(result.proposed_files)
    changed["docs/notes.md"] = "someone edited the file\n"
    with pytest.raises(ValueError, match="preimage"):
        preview_text_rollback(
            result, changed, principal_id="owner", task_id="t1",
        )


def test_cross_principal_task_and_fake_approval_denied():
    _, _, result = preview()
    for principal, task in (("other", "t1"), ("owner", "other")):
        with pytest.raises(PermissionError, match="scope"):
            preview_text_rollback(
                result, dict(result.proposed_files),
                principal_id=principal, task_id=task,
            )
    with pytest.raises(ValueError, match="forged"):
        preview_text_rollback(
            replace(result, authorization_checked=True),
            dict(result.proposed_files), principal_id="owner", task_id="t1",
        )


def test_ambiguous_change_missing_target_and_duplicate_patch_denied():
    files = {"src/a": "a a a"}
    change = TextPatchRequest("src/a", digest(files["src/a"]), "a", "b")
    with pytest.raises(ValueError, match="ambiguous"):
        preview_text_transaction(files, (change,), principal_id="owner", task_id="t1")
    with pytest.raises(ValueError):
        preview_text_transaction(
            {"src/a": "only"}, (TextPatchRequest(
                "missing", digest("only"), "only", "new"
            ),), principal_id="owner", task_id="t1",
        )
    with pytest.raises(ValueError):
        preview_text_transaction(
            {"src/a": "only"}, (TextPatchRequest(
                "src/a", digest("only"), "only", "new"
            ), TextPatchRequest("src/a", digest("only"), "only", "new")),
            principal_id="owner", task_id="t1",
        )


@pytest.mark.parametrize("path", [
    "../secrets", "/root", "src\\shell", "src//a", "C:drive", "src/./app",
])
def test_unsafe_paths_fail_closed(path):
    with pytest.raises(ValueError):
        preview_text_transaction(
            {path: "old"}, (TextPatchRequest(
                path, digest("old"), "old", "new"
            ),), principal_id="owner", task_id="t1",
        )


def test_path_case_collision_denied():
    with pytest.raises(ValueError, match="duplicate"):
        preview_text_transaction(
            {"A.txt": "old", "a.TXT": "other"},
            (TextPatchRequest("A.txt", digest("old"), "old", "new"),),
            principal_id="owner", task_id="t1",
        )


def test_unicode_roundtrip_and_no_op_rejected():
    files = {"src/notes.txt": "Türkçe güvenli"}
    result = preview_text_transaction(
        files, (TextPatchRequest(
            "src/notes.txt", digest(files["src/notes.txt"]),
            "güvenli", "çalışıyor",
        ),), principal_id="owner", task_id="t1",
    )
    assert preview_text_rollback(
        result, dict(result.proposed_files),
        principal_id="owner", task_id="t1",
    ) == files
    with pytest.raises(ValueError):
        preview_text_transaction(
            files, (TextPatchRequest(
                "src/notes.txt", digest(files["src/notes.txt"]),
                "güvenli", "güvenli",
            ),), principal_id="owner", task_id="t1",
        )


def test_boolean_limits_and_type_confused_data_denied():
    with pytest.raises(ValueError):
        preview_text_transaction(
            {"src/a": "old"},
            (TextPatchRequest("src/a", True, "old", "new"),),
            principal_id="owner", task_id="t1",
        )
    with pytest.raises(ValueError):
        preview_text_transaction(
            {"src/a": b"old"},
            (TextPatchRequest("src/a", digest("old"), "old", "new"),),
            principal_id="owner", task_id="t1",
        )
