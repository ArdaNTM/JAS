"""Fail-closed acceptance ledger validation for AURA's 117-feature program.

This tool checks engineering evidence metadata only. It does not execute code,
grant capabilities, or claim that a feature is implemented in the runtime.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA = "aura.feature-tracker.v1"
STATUSES = {
    "NOT_STARTED", "RESEARCHING", "DESIGNED", "IMPLEMENTING", "IMPLEMENTED",
    "TESTING", "FAILED", "BLOCKED", "COMPLETED",
}
ASSESSMENTS = {"NOT_ASSESSED", "PARTIAL_VERIFIED", "VERIFIED"}
FIELDS = {
    "id", "name", "phase", "status", "assessment", "dependencies",
    "code_paths", "documentation_paths", "test_commands", "test_results",
    "security_review", "acceptance", "commit", "pull_request", "blockers",
    "technical_goal", "user_capability", "integration", "hardware_requirements",
    "license_review", "local_offline", "notes",
    "existing_jas_state", "proposed_technology", "license_terms",
    "commercial_terms", "integration_test_criteria", "unit_test_criteria",
    "security_test_criteria", "acceptance_criteria", "performance_requirements",
    "complexity", "known_limitations", "missing_components", "official_links",
    "alternatives",
}
LIST_FIELDS = {
    "dependencies", "code_paths", "documentation_paths", "test_commands",
    "blockers", "missing_components", "official_links", "alternatives",
}
TEXT_FIELDS = FIELDS - LIST_FIELDS - {"id", "phase"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate(data: object) -> None:
    _require(type(data) is dict and set(data) == {
        "schema", "scope", "baseline_ref", "status_semantics", "features"
    }, "invalid tracker envelope")
    _require(data["schema"] == SCHEMA and data["scope"] == "ArdaNTM/JAS",
             "unexpected repository or schema")
    _require(type(data["baseline_ref"]) is str
             and re.fullmatch(r"[0-9a-f]{40}", data["baseline_ref"]) is not None,
             "missing pinned baseline")
    _require(type(data["status_semantics"]) is str
             and bool(data["status_semantics"].strip()), "status semantics required")
    records = data["features"]
    _require(type(records) is list and len(records) == 117,
             "exactly 117 numbered features required")
    dependencies: dict[int, list[int]] = {}
    for expected_id, record in enumerate(records, 1):
        _require(type(record) is dict and set(record) == FIELDS,
                 f"unexpected fields for feature {expected_id}")
        _require(type(record["id"]) is int and record["id"] == expected_id,
                 f"duplicate, missing or out-of-order feature {expected_id}")
        _require(type(record["phase"]) is int and 1 <= record["phase"] <= 9,
                 f"invalid phase for {expected_id}")
        _require(all(type(record[field]) is str for field in TEXT_FIELDS),
                 f"invalid text field for {expected_id}")
        _require(bool(record["name"].strip()) and len(record["name"]) <= 200,
                 f"invalid feature name for {expected_id}")
        _require(record["status"] in STATUSES and
                 record["assessment"] in ASSESSMENTS,
                 f"invalid status for {expected_id}")
        for field in LIST_FIELDS:
            _require(type(record[field]) is list,
                     f"{field} must be list for {expected_id}")
        for field in LIST_FIELDS - {"dependencies"}:
            _require(all(type(value) is str and bool(value.strip())
                         for value in record[field]),
                     f"invalid {field} entry for {expected_id}")
        deps = record["dependencies"]
        _require(all(type(dep) is int and 1 <= dep <= 117 and dep != expected_id
                     for dep in deps) and len(set(deps)) == len(deps),
                 f"invalid dependencies for {expected_id}")
        dependencies[expected_id] = deps
        if record["status"] == "COMPLETED":
            _require(record["assessment"] == "VERIFIED"
                     and record["acceptance"] == "PASS"
                     and record["test_results"] == "PASS"
                     and record["security_review"] == "PASS"
                     and bool(record["test_commands"])
                     and bool(record["code_paths"])
                     and not record["blockers"]
                     and re.fullmatch(r"[0-9a-f]{40}", record["commit"]) is not None
                     and re.fullmatch(
                         r"https://github[.]com/ArdaNTM/JAS/pull/[1-9][0-9]*",
                         record["pull_request"]) is not None,
                     f"feature {expected_id} claims completion without evidence")

    state: dict[int, int] = {}

    def visit(node: int) -> None:
        if state.get(node) == 1:
            raise ValueError(f"circular feature dependency involving {node}")
        if state.get(node) == 2:
            return
        state[node] = 1
        for dependency in dependencies[node]:
            visit(dependency)
        state[node] = 2

    for feature_id in range(1, 118):
        visit(feature_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate AURA 117-feature evidence tracker")
    parser.add_argument(
        "--file", type=Path,
        default=Path(__file__).resolve().parents[1] /
                "docs/22_IMPLEMENTATION/AURA_FEATURE_TRACKER.json",
    )
    args = parser.parse_args(argv)
    try:
        raw = args.file.read_bytes()
        if len(raw) > 512_000:
            raise ValueError("tracker exceeds size cap")
        document = json.loads(raw.decode("utf-8"))
        validate(document)
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    print("PASS: 117 feature entries validated; no unproven COMPLETED claims")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
