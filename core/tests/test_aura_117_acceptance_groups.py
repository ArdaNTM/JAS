"""Regression for release gate: CI success cannot silently claim Owner acceptance."""
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
        "group_A_complete": 0,
        "group_B_testing": 108,
        "total_verified_ready": 0,
    }


def test_real_group_a_is_still_blocked_on_missing_acceptance():
    tracker, _, _ = load()
    for record in tracker["features"]:
        if record["id"] in audit.SOFTWARE_IDS:
            assert not audit.eligible_for_completion(record)
            assert record["status"] == "TESTING"
            assert record["missing_components"] or record["blockers"]


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



def test_B1_completed_needs_same_independent_security_and_owner_evidence():
    tracker, groups, provenance = load()
    sample = copy.deepcopy(tracker["features"][9])  # #10 is a B1-only candidate
    assert sample["id"] == 10 and sample["status"] == "TESTING"
    assert not audit.eligible_for_completion(sample)
    sample["status"] = "COMPLETED"
    forged = copy.deepcopy(tracker)
    forged["features"][9] = sample
    with pytest.raises(ValueError, match="unproven"):
        audit.validate(forged, groups, provenance)
    # Even if a caller edits a few status fields, surviving missing work blocks it.
    sample.update({
        "assessment": "VERIFIED", "acceptance": "PASS",
        "test_results": "PASS", "security_review": "PASS",
        "license_review": "NOT_APPLICABLE",
        "hardware_review": "NOT_APPLICABLE",
    })
    assert sample["missing_components"]
    assert not audit.eligible_for_completion(sample)


def test_marking_feature_completed_without_evidence_fails_closed():
    tracker, groups, provenance = load()
    fake = copy.deepcopy(tracker)
    fake["features"][1]["status"] = "COMPLETED"
    with pytest.raises(ValueError, match="unproven"):
        audit.validate(fake, groups, provenance)


def test_completed_metadata_cannot_substitute_missing_security_or_e2e():
    tracker, _, _ = load()
    fake = copy.deepcopy(tracker["features"][1])
    fake.update({
        "status": "COMPLETED", "assessment": "VERIFIED",
        "acceptance": "PASS", "test_results": "PASS",
        "security_review": "PASS", "license_review": "NOT_APPLICABLE",
        "hardware_review": "NOT_APPLICABLE",
    })
    assert not audit.eligible_for_completion(fake)
    fake["missing_components"] = []
    assert audit.eligible_for_completion(fake)
    fake["blockers"] = ["unresolved source conflict"]
    assert not audit.eligible_for_completion(fake)


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
