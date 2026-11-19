"""Fail-closed software completion eligibility and provenance audit for AURA.

This does not certify production authorization. It refuses to infer COMPLETED
from CI-only or from membership in the software-only candidate group.
Canonical tracker and release lock remain separate sources of truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACKER = ROOT / "docs/22_IMPLEMENTATION/AURA_FEATURE_TRACKER.json"
GROUPS = ROOT / "docs/22_IMPLEMENTATION/AURA_ACCEPTANCE_GROUPS.json"
PROVENANCE = ROOT / "docs/22_IMPLEMENTATION/AURA_CORE_PROVENANCE_RECONCILIATION.json"
SOFTWARE_IDS = frozenset({2, 5, 40, 44, 47, 59, 67, 73, 111})
B1_IDS = frozenset({8, 10, 12, 21, 35, 36, 37, 38, 39, 41, 42, 43, 52, 53, 62, 65, 66, 76, 102, 112})
B2_TRACKS = frozenset({"B2-Owner", "B2-Env"})
B2_OWNER_IDS = frozenset({34, 46, 50, 58, 61, 64, 68, 70, 71, 72, 74, 75, 108, 109, 110, 114, 117})
B2_ENV_SOFTWARE_IDS = frozenset({3, 4, 15, 29, 30, 48, 56, 63, 103, 105, 107, 115})
B2_ENV_SIMULATION_IDS = frozenset({81, 85, 86, 87, 88, 89, 90})
B2_ENV_ACCEPTED = B2_ENV_SOFTWARE_IDS | B2_ENV_SIMULATION_IDS
APPROVED_ENV_MAIN_MERGE = "5e51d3f50b53f482e14e3d1d73a375d08e6e9eb7"
APPROVED_ENV_REGRESSION_HEAD = "7beeb4a7c95e6b571fddeae95ef5b802b624cd8f"
APPROVED_MAIN_MERGE = "b09ad74c49ebe1d73e2bb79524c8c8006e2ca40f"


def read_json(path: Path) -> dict:
    raw = path.read_bytes()
    if len(raw) > 512_000:
        raise ValueError("acceptance source exceeds 512 KiB")
    result = json.loads(raw.decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError("acceptance source must be an object")
    return result


def eligible_for_completion(record: dict) -> bool:
    """Bounded A/B1/B2-Owner eligibility only; never attests live operation."""
    return (
        record.get("id") in SOFTWARE_IDS | B1_IDS | B2_OWNER_IDS | B2_ENV_ACCEPTED
        and (record.get("id") not in B2_OWNER_IDS
             or (APPROVED_MAIN_MERGE in record.get("notes", "")
                 and record.get("known_limitations", "").startswith("V2 /")))
        and (record.get("id") not in B2_ENV_ACCEPTED or (
            APPROVED_ENV_MAIN_MERGE in record.get("notes", "")
            and APPROVED_ENV_REGRESSION_HEAD in record.get("notes", "")
            and record.get("known_limitations", "").startswith("V2 /")
            and (record.get("id") not in B2_ENV_SIMULATION_IDS
                 or ("SIMULATION_ONLY" in record.get("notes", "")
                     and any(term in record.get("technical_goal", "").lower()
                             for term in ("synthetic", "simulated"))))
        ))
        and record.get("assessment") == "VERIFIED"
        and record.get("acceptance") == "PASS"
        and record.get("security_review") == "PASS"
        and record.get("test_results") == "PASS"
        and record.get("license_review") in {"PASS", "NOT_APPLICABLE"}
        and record.get("hardware_review") in {"PASS", "NOT_APPLICABLE"}
        and isinstance(record.get("code_paths"), list) and bool(record["code_paths"])
        and isinstance(record.get("test_commands"), list) and bool(record["test_commands"])
        and isinstance(record.get("blockers"), list) and not record["blockers"]
        and isinstance(record.get("missing_components"), list) and not record["missing_components"]
        and isinstance(record.get("commit"), str) and len(record["commit"]) == 40
        and isinstance(record.get("pull_request"), str)
        and record["pull_request"].startswith("https://github.com/ArdaNTM/JAS/pull/")
        and record.get("technical_goal") not in {"", "NOT_ASSESSED"}
        and record.get("acceptance_criteria") not in {"", "NOT_ASSESSED"}
        and record.get("security_test_criteria") not in {"", "NOT_ASSESSED"}
    )


def git_blob_sha(data: bytes) -> str:
    """Git blob digest, not a raw-file SHA-1; CI can verify without GitHub API."""
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def validate(tracker: dict, groups: dict, provenance: dict, root: Path = ROOT) -> dict:
    if len(tracker.get("features", [])) != 117:
        raise ValueError("tracker cardinality changed")
    features = tracker["features"]
    actual_ids = [f["id"] for f in features]
    if actual_ids != list(range(1, 118)):
        raise ValueError("tracker feature IDs are not canonical")

    if groups.get("schema") != "aura.acceptance-groups.v1" or groups.get("scope") != "ArdaNTM/JAS":
        raise ValueError("invalid group catalog")
    a_ids = groups.get("A_ids")
    b_ids = groups.get("B_ids")
    if a_ids != sorted(SOFTWARE_IDS):
        raise ValueError("software Group A candidate boundary changed without audit")
    if b_ids != [i for i in range(1, 118) if i not in SOFTWARE_IDS]:
        raise ValueError("Group B coverage is not the exact complement")
    if groups.get("B1_ids") != sorted(B1_IDS):
        raise ValueError("B1 subgroup candidate boundary changed")
    b2_ids = sorted(set(b_ids) - B1_IDS)
    if groups.get("B2_ids") != b2_ids or set(b_ids) != B1_IDS | set(b2_ids):
        raise ValueError("B1/B2 subgroups do not partition all B features")
    owner_ids, env_ids = groups.get("B2_owner_ids"), groups.get("B2_env_ids")
    if (type(owner_ids) is not list or type(env_ids) is not list
            or owner_ids != sorted(set(owner_ids))
            or env_ids != sorted(set(env_ids))
            or set(owner_ids) & set(env_ids)
            or set(owner_ids) | set(env_ids) != set(b2_ids)):
        raise ValueError("B2-Owner/B2-Env partition must cover exactly 88 records")
    if set(owner_ids) != B2_OWNER_IDS:
        raise ValueError("B2-Owner frozen cohort mismatch")
    # B2-Env validation locations are scheduling targets, never acceptances.
    validation_groups = groups.get("B2_env_validation_groups")
    expected_groups = ("windows_local", "hyperv_docker", "external_hardware_simulation")
    if type(validation_groups) is not dict or set(validation_groups) != set(expected_groups):
        raise ValueError("B2-Env validation groups absent or incomplete")
    group_ids = []
    for key in expected_groups:
        assigned = validation_groups[key]
        if (type(assigned) is not list
                or any(type(item) is not int for item in assigned)
                or assigned != sorted(set(assigned))):
            raise ValueError("B2-Env validation group IDs invalid")
        group_ids.extend(assigned)
    if len(group_ids) != len(set(group_ids)) or set(group_ids) != set(env_ids):
        raise ValueError("B2-Env validation groups overlap or are incomplete")
    if validation_groups["hyperv_docker"] != [25, 27, 33, 45, 51, 60, 101]:
        raise ValueError("B2-Env Docker trust boundary was reclassified")
    if validation_groups["external_hardware_simulation"] != [81, 85, 86, 87, 88, 89, 90]:
        raise ValueError("B2-Env physical trust boundary was reclassified")
    # Exact Owner-approved bounded B2-Env v1 subcohorts; never infer real hardware.
    env_acceptance = groups.get("B2_env_acceptance")
    if not isinstance(env_acceptance, dict) or (
        env_acceptance.get("software_ids") != sorted(B2_ENV_SOFTWARE_IDS)
        or env_acceptance.get("simulation_ids") != sorted(B2_ENV_SIMULATION_IDS)
        or env_acceptance.get("remaining_ids") != sorted(set(env_ids) - B2_ENV_ACCEPTED)
        or env_acceptance.get("owner_main_merge") != APPROVED_ENV_MAIN_MERGE
        or env_acceptance.get("merged_ci_head") != APPROVED_ENV_REGRESSION_HEAD
        or "NO_PHYSICAL_CERTIFICATION" not in env_acceptance.get("simulation_policy", "")
    ):
        raise ValueError("B2-Env Owner v1 acceptance scope/consent mismatch")
    rows = groups.get("records")
    if not isinstance(rows, list) or len(rows) != 117:
        raise ValueError("group records must cover all 117 features")
    for record, entry in zip(features, rows, strict=True):
        expected_group = "A" if record["id"] in SOFTWARE_IDS else "B"
        subgroup = None if expected_group == "A" else ("B1" if record["id"] in B1_IDS else "B2")
        if (entry.get("id") != record["id"] or entry.get("name") != record["name"]
                or entry.get("group") != expected_group or entry.get("subgroup") != subgroup):
            raise ValueError("feature grouping does not match authoritative tracker")
        if subgroup == "B2":
            expected_track = "B2-Owner" if record["id"] in owner_ids else "B2-Env"
            if entry.get("b2_acceptance_track") != expected_track:
                raise ValueError("B2 readiness/Owner-Env track mismatch")
            if expected_track == "B2-Env":
                accepted_v1 = record["id"] in B2_ENV_ACCEPTED
                if (entry.get("ready_for_completion") is not accepted_v1
                        or record["status"] != ("COMPLETED" if accepted_v1 else "TESTING")
                        or accepted_v1 and not eligible_for_completion(record)):
                    raise ValueError("B2 readiness: B2-Env v1 status must be evidenced")
            elif (entry.get("ready_for_completion") is not True
                  or record["status"] != "COMPLETED"
                  or not eligible_for_completion(record)):
                raise ValueError("B2-Owner bounded v1 completion evidence incomplete")
        elif "b2_acceptance_track" in entry:
            raise ValueError("non-B2 feature must not have B2 readiness track")
        expected_marker = f"[ACCEPTANCE_GROUP={expected_group};"
        if not isinstance(record.get("notes"), str) or not record["notes"].startswith(expected_marker):
            raise ValueError("authoritative feature tracker missing Group A/B classification")
        ready = eligible_for_completion(record)
        if entry.get("ready_for_completion") is not ready:
            raise ValueError("completion readiness flag not supported by evidence")
        if record["status"] == "COMPLETED" and not ready:
            raise ValueError("unproven feature marked COMPLETED")

    if provenance.get("schema") != "aura.core-reconciliation.v1":
        raise ValueError("missing canonical provenance")
    paths = provenance.get("files")
    if not isinstance(paths, list) or len(paths) != 5:
        raise ValueError("incomplete security-sensitive source lineage")
    for entry in paths:
        path = entry.get("path")
        if not isinstance(path, str) or not path.startswith("core/src/aura_core/") or ".." in path:
            raise ValueError("invalid tracked source path")
        absolute = root / path
        actual = git_blob_sha(absolute.read_bytes())
        if actual != entry.get("unified_blob_sha"):
            raise ValueError(f"canonical source changed without review: {path}")
        variants = entry.get("variants")
        if not isinstance(variants, list) or not variants:
            raise ValueError("missing alternative source lineage")
        if not any(v.get("blob") == actual for v in variants):
            raise ValueError("no canonical source pin corresponds to current source")
    return {
        "group_A": len(SOFTWARE_IDS),
        "group_B": 117 - len(SOFTWARE_IDS),
        "group_B1": len(B1_IDS),
        "group_B2": 117 - len(SOFTWARE_IDS) - len(B1_IDS),
        "group_A_complete": sum(f["status"] == "COMPLETED" for f in features if f["id"] in SOFTWARE_IDS),
        "group_B_testing": sum(f["status"] == "TESTING" for f in features if f["id"] not in SOFTWARE_IDS),
        "total_completed": sum(f["status"] == "COMPLETED" for f in features),
        "B2_owner": len(owner_ids), "B2_env": len(env_ids),
        "B2_env_software_v1": len(B2_ENV_SOFTWARE_IDS),
        "B2_env_simulation_v1": len(B2_ENV_SIMULATION_IDS),
        "B2_env_testing": len(set(env_ids) - B2_ENV_ACCEPTED),
        "B2_windows_local": len(validation_groups["windows_local"]),
        "B2_hyperv_docker": len(validation_groups["hyperv_docker"]),
        "B2_external_hardware": len(validation_groups["external_hardware_simulation"]),
        "total_verified_ready": sum(eligible_for_completion(f) for f in features),
    }


def main() -> int:
    try:
        summary = validate(read_json(TRACKER), read_json(GROUPS), read_json(PROVENANCE))
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        print(f"FAIL: {exc}")
        return 2
    print("PASS: 117-feature A/B inventory and canonical source blob pins validated")
    print("A={group_A} B1={group_B1} B2={group_B2} COMPLETED={total_completed} ELIGIBLE={total_verified_ready} B2-Owner={B2_owner} B2-Env={B2_env}".format(**summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
