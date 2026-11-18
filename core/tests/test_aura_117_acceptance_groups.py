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
        "group_B_testing": 98,
        "total_verified_ready": 19,
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
        if record["id"] not in audit.SOFTWARE_IDS | audit.B1_IDS:
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
    assert fake["features"][41]["status"] == "TESTING"  # #42 remains B1 unready.
    fake["features"][41]["status"] = "COMPLETED"
    with pytest.raises(ValueError, match="unproven"):
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
