"""Regression for frozen v1 completion and fail-closed security evidence gates."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "aura_completion_audit", ROOT / "scripts" / "audit_aura_117_completion.py"
)
assert spec is not None and spec.loader is not None
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def load():
    return (
        audit.read_json(audit.TRACKER),
        audit.read_json(audit.GROUPS),
        audit.read_json(audit.PROVENANCE),
    )


def test_117_features_partition_and_pinned_canonical_sources():
    tracker, groups, provenance = load()
    summary = audit.validate(tracker, groups, provenance)
    assert summary == {
        "group_A": 9,
        "group_B": 108,
        "group_B1": 20,
        "group_B2": 88,
        "group_A_complete": 9,
        "group_B_testing": 71,
        "total_completed": 46,
        "B2_owner": 17,
        "B2_env": 71,
        "total_verified_ready": 46,
    }


def test_group_a_owner_frozen_v1_is_evidenced_but_future_scope_not_certified():
    tracker, _, _ = load()
    for record in tracker["features"]:
        if record["id"] in audit.SOFTWARE_IDS:
            assert audit.eligible_for_completion(record)
            assert record["status"] == "COMPLETED"
            assert record["missing_components"] == []
            assert record["blockers"] == []
            assert "V2" in record["known_limitations"]
    for record in tracker["features"]:
        if record["id"] not in audit.SOFTWARE_IDS | audit.B1_IDS | audit.B2_OWNER_IDS:
            assert record["status"] == "TESTING"


def test_rejects_subgroup_overlap_and_mislabel():
    tracker, groups, provenance = load()
    bad = copy.deepcopy(groups)
    bad["B1_ids"].append(91)
    with pytest.raises(ValueError, match="B1"):
        audit.validate(tracker, bad, provenance)
    bad = copy.deepcopy(groups)
    bad["records"][0]["subgroup"] = "B1"  # Feature #1 is B2.
    with pytest.raises(ValueError, match="grouping"):
        audit.validate(tracker, bad, provenance)


def test_rejects_wrong_or_duplicate_grouping():
    tracker, groups, provenance = load()
    bad = copy.deepcopy(groups)
    bad["A_ids"] = bad["A_ids"] + [111]
    with pytest.raises(ValueError, match="boundary"):
        audit.validate(tracker, bad, provenance)
    bad = copy.deepcopy(groups)
    bad["records"][0]["group"] = "A"
    with pytest.raises(ValueError, match="grouping"):
        audit.validate(tracker, bad, provenance)



def test_B1_frozen_v1_completion_requires_all_existing_gates():
    tracker, groups, provenance = load()
    sample = copy.deepcopy(tracker["features"][9])  # #10 accepted narrow B1
    assert sample["id"] == 10 and sample["status"] == "COMPLETED"
    assert audit.eligible_for_completion(sample)
    for name, bad in (
        ("security_review", "NOT_REVIEWED"),
        ("acceptance", "NOT_VERIFIED"),
        ("test_results", "FAIL"),
        ("license_review", "NOT_REVIEWED"),
    ):
        fake = copy.deepcopy(tracker)
        fake["features"][9][name] = bad
        assert not audit.eligible_for_completion(fake["features"][9])
        with pytest.raises(ValueError, match="completion readiness"):
            audit.validate(fake, groups, provenance)


def test_marking_unready_feature_completed_fails_closed():
    tracker, groups, provenance = load()
    fake = copy.deepcopy(tracker)
    assert fake["features"][0]["status"] == "TESTING"  # #1 remains B2 unready.
    fake["features"][0]["status"] = "COMPLETED"
    with pytest.raises(ValueError, match="B2 readiness"):
        audit.validate(fake, groups, provenance)


def test_completed_metadata_never_substitutes_missing_security_or_e2e():
    tracker, _, _ = load()
    fake = copy.deepcopy(tracker["features"][1])  # #2 v1 truly eligible.
    assert audit.eligible_for_completion(fake)
    fake["missing_components"] = ["unauthorized action not covered by v1"]
    assert not audit.eligible_for_completion(fake)
    fake["missing_components"] = []
    fake["blockers"] = ["unresolved source conflict"]
    assert not audit.eligible_for_completion(fake)
    fake["blockers"] = []
    fake["security_review"] = "PARTIAL_VERIFIED"
    assert not audit.eligible_for_completion(fake)
    fake["security_review"] = "PASS"
    assert audit.eligible_for_completion(fake)



def test_last_ten_B1_bounded_v1_and_b2_remain_unready():
    tracker, groups, _ = load()
    last = {42, 43, 52, 53, 62, 65, 66, 76, 102, 112}
    for item in tracker["features"]:
        if item["id"] in last:
            assert item["status"] == "COMPLETED"
            assert audit.eligible_for_completion(item)
            assert not item["missing_components"] and not item["blockers"]
            assert groups["records"][item["id"] - 1]["ready_for_completion"] is True
        if item["id"] in groups["B2_env_ids"]:
            assert item["status"] == "TESTING"
            assert not audit.eligible_for_completion(item)
            assert groups["records"][item["id"] - 1]["ready_for_completion"] is False
        if item["id"] in groups["B2_owner_ids"]:
            assert item["status"] == "COMPLETED"
            assert audit.eligible_for_completion(item)
            assert groups["records"][item["id"] - 1]["ready_for_completion"] is True


def test_b2_partition_tamper_and_spoofed_ready_fail_closed():
    tracker, groups, provenance = load()
    bad = copy.deepcopy(groups)
    bad["B2_env_ids"].append(bad["B2_owner_ids"][0])
    with pytest.raises(ValueError, match="B2-Owner/B2-Env"):
        audit.validate(tracker, bad, provenance)
    bad = copy.deepcopy(groups)
    target_id = bad["B2_owner_ids"][0]
    bad["records"][target_id - 1]["b2_acceptance_track"] = "B2-Env"
    with pytest.raises(ValueError, match="B2 readiness"):
        audit.validate(tracker, bad, provenance)
    bad = copy.deepcopy(groups)
    bad["records"][target_id - 1]["ready_for_completion"] = False
    with pytest.raises(ValueError, match="B2-Owner"):
        audit.validate(tracker, bad, provenance)
    bad = copy.deepcopy(groups)
    env_target = bad["B2_env_ids"][0]
    bad["records"][env_target - 1]["ready_for_completion"] = True
    with pytest.raises(ValueError, match="B2-Env"):
        audit.validate(tracker, bad, provenance)

def test_source_pin_mismatch_rejected_before_feature_completion():
    tracker, groups, provenance = load()
    fake = copy.deepcopy(provenance)
    fake["files"][0]["unified_blob_sha"] = "0" * 40
    with pytest.raises(ValueError, match="canonical source changed"):
        audit.validate(tracker, groups, fake)


def test_source_path_escape_fails_closed():
    tracker, groups, provenance = load()
    fake = copy.deepcopy(provenance)
    fake["files"][0]["path"] = "core/src/aura_core/../../secret"
    with pytest.raises(ValueError, match="invalid tracked source path"):
        audit.validate(tracker, groups, fake)



def test_b2_owner_v1_requires_real_merge_pin_and_review_evidence():
    tracker, groups, provenance = load()
    for owner_id in groups["B2_owner_ids"]:
        item = tracker["features"][owner_id - 1]
        assert item["status"] == "COMPLETED"
        assert audit.eligible_for_completion(item)
        assert item["known_limitations"].startswith("V2 /")
        assert audit.APPROVED_MAIN_MERGE in item["notes"]
        assert item["missing_components"] == []
    fake = copy.deepcopy(tracker)
    first = groups["B2_owner_ids"][0] - 1
    fake["features"][first]["notes"] = fake["features"][first]["notes"].replace(
        audit.APPROVED_MAIN_MERGE, "0" * 40)
    with pytest.raises(ValueError, match="B2-Owner"):
        audit.validate(fake, groups, provenance)
    fake = copy.deepcopy(tracker)
    fake["features"][first]["security_review"] = "NOT_REVIEWED"
    with pytest.raises(ValueError, match="B2-Owner"):
        audit.validate(fake, groups, provenance)
