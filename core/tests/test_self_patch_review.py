"""Real source patch review: no model output is imported or executed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from aura_core.evolution.self_patch_review import SelfPatchReview, PatchRejected, export_review_patch


REL = "core/src/aura_core/research/citations.py"
SOURCE = "def _escape_markdown(value: str) -> str:\n    return value\n"
RESPONSE = {
    "summary": "Escape markdown punctuation",
    "old": "    return value",
    "new": "    return value.replace('*', r'\\*')",
    "test_plan": "Verify literal asterisk escaping and unchanged ordinary text.",
}


@pytest.fixture
def review(tmp_path, monkeypatch):
    checkout = tmp_path / "JAS"
    source = checkout / REL
    source.parent.mkdir(parents=True)
    source.write_bytes(SOURCE.encode())
    identity = hashlib.sha256(source.read_bytes()).hexdigest()
    rows = [{"path": REL, "sha256": identity}]
    release = hashlib.sha256((REL + "\t" + identity + "\n").encode()).hexdigest()
    (checkout / "release-manifest.final.json").write_text(json.dumps({
        "algorithm": "SHA-256", "release_digest": "sha256:" + release,
        "file_count": 1, "files": rows,
    }))
    directory = tmp_path / "review"
    directory.mkdir(mode=0o700)
    import os
    if os.name == "nt":
        from test_evolution_decision_engine import _private_windows_test_owner_state
        # Native ACL acceptance belongs to the independently provisioned
        # Windows release operator. These portable tests emulate only ACL IO.
        from aura_core.evolution import windows_owner_storage
        monkeypatch.setattr(windows_owner_storage, "require_private_acl", lambda _: None)
        monkeypatch.setattr(windows_owner_storage, "harden_private_acl", lambda _: None)
    return SelfPatchReview(checkout, directory), checkout, directory


def test_real_patch_is_digest_bound_and_checkout_remains_unchanged(review):
    queue, checkout, directory = review
    base = queue.read_target(REL)
    item = queue.stage(base, RESPONSE)
    assert item["authorization_granted"] is False
    assert item["execution_performed"] is False
    assert item["state"] == "NEEDS_OWNER_REVIEW"
    assert (checkout / REL).read_text() == SOURCE
    draft = directory / (item["draft_id"] + ".patch-review.json")
    patch = export_review_patch(checkout, draft, expected_id=item["draft_id"])
    assert "--- a/" + REL in patch and "+++ b/" + REL in patch
    assert "-    return value" in patch and "+    return value.replace" in patch
    assert queue.pending()[0]["draft_id"] == item["draft_id"]
    assert "new" not in queue.pending()[0]
    assert queue.stage(base, RESPONSE)["draft_id"] == item["draft_id"]
    assert len(list(directory.glob("*.patch-review.json"))) == 1


@pytest.mark.parametrize("update", [
    {"old": "def _escape_markdown(value: str) -> str:"},
    {"old": "    return missing"},
    {"new": "    import os\n    return value"},
    {"new": "    return value\n\ndef other():\n    return 1"},
    {"new": "    return ("},
    {"new": "    return value"},
    {"test_plan": ""},
    {"path": "core/src/aura_core/kernel/permissions.py"},
])
def test_reject_invalid_or_out_of_scope_patch(review, update):
    queue, _, directory = review
    with pytest.raises((PatchRejected, ValueError)):
        queue.stage(queue.read_target(REL), {**RESPONSE, **update})
    assert not list(directory.glob("*.patch-review.json"))


def test_reject_protected_paths_and_stale_or_tampered_review(review):
    queue, checkout, directory = review
    for path in ("core/src/aura_core/kernel/permissions.py", "../outside.py",
                 "core/src/aura_core/evolution/self_patch_review.py"):
        with pytest.raises(PatchRejected):
            queue.read_target(path)
    item = queue.stage(queue.read_target(REL), RESPONSE)
    draft = directory / (item["draft_id"] + ".patch-review.json")
    original = draft.read_bytes()
    doc = json.loads(original)
    doc["change"]["new"] = "    return 'tampered'"
    draft.write_text(json.dumps(doc))
    with pytest.raises(PatchRejected):
        export_review_patch(checkout, draft, expected_id=item["draft_id"])
    draft.write_bytes(original)
    (checkout / REL).write_text(SOURCE + "# changed\n")
    with pytest.raises(PatchRejected):
        export_review_patch(checkout, draft, expected_id=item["draft_id"])


@pytest.mark.asyncio
async def test_provider_neutral_model_stages_data_without_execution(review):
    queue, checkout, directory = review
    model = SimpleNamespace(complete_json=AsyncMock(return_value=RESPONSE))
    result = await queue.propose_once(model, timeout=5)
    assert result["state"] == "NEEDS_OWNER_REVIEW"
    model.complete_json.assert_awaited_once()
    assert "untrusted_source" in model.complete_json.call_args.kwargs["user_prompt"]
    assert (checkout / REL).read_text() == SOURCE
    assert len(list(directory.glob("*.patch-review.json"))) == 1
