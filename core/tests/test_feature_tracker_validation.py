"""Executable regressions for the AURA feature ledger safety contract."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_aura_feature_tracker.py"
TRACKER = ROOT / "docs" / "22_IMPLEMENTATION" / "AURA_FEATURE_TRACKER.json"
spec = importlib.util.spec_from_file_location("aura_tracker_validator", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def load():
    return json.loads(TRACKER.read_text(encoding="utf-8"))


def test_real_117_feature_tracker_validates():
    module.validate(load())


def test_missing_feature_fails_closed():
    doc = load()
    doc["features"].pop()
    with pytest.raises(ValueError, match="117"):
        module.validate(doc)


def test_reordering_or_duplicate_id_fails_closed():
    doc = load()
    doc["features"][1]["id"] = 1
    with pytest.raises(ValueError, match="duplicate"):
        module.validate(doc)


def test_completion_requires_real_evidence():
    doc = load()
    doc["features"][0]["status"] = "COMPLETED"
    with pytest.raises(ValueError, match="without evidence"):
        module.validate(doc)


def test_unknown_dependency_fails_closed():
    doc = load()
    doc["features"][0]["dependencies"] = [118]
    with pytest.raises(ValueError, match="dependencies"):
        module.validate(doc)


def test_cycle_fails_closed():
    doc = load()
    doc["features"][0]["dependencies"] = [2]
    doc["features"][1]["dependencies"] = [1]
    with pytest.raises(ValueError, match="circular"):
        module.validate(doc)


def test_rejects_implicit_bool_as_feature_id():
    doc = load()
    doc["features"][0]["id"] = True
    with pytest.raises(ValueError, match="feature"):
        module.validate(doc)


def test_rejects_missing_required_design_or_license_fields():
    doc = load()
    doc["features"][0].pop("license_terms")
    with pytest.raises(ValueError, match="unexpected fields"):
        module.validate(doc)


def test_completed_feature_must_have_security_and_acceptance_evidence():
    doc = load()
    item = doc["features"][0]
    item["status"] = "COMPLETED"
    item["assessment"] = "VERIFIED"
    item["test_results"] = "PASS"
    item["acceptance"] = "PASS"
    item["commit"] = "1" * 40
    item["pull_request"] = "https://github.com/ArdaNTM/JAS/pull/66"
    item["code_paths"] = ["core/src/example.py"]
    item["test_commands"] = ["pytest"]
    with pytest.raises(ValueError, match="without evidence"):
        module.validate(doc)


def test_completed_requires_license_hardware_and_explicit_criteria():
    doc = load()
    item = doc["features"][0]
    item.update({
        "status": "COMPLETED", "assessment": "VERIFIED",
        "acceptance": "PASS", "test_results": "PASS", "security_review": "PASS",
        "commit": "1" * 40,
        "pull_request": "https://github.com/ArdaNTM/JAS/pull/66",
        "code_paths": ["core/src/example.py"], "test_commands": ["pytest"],
        "technical_goal": "A specific goal", "acceptance_criteria": "A passed check",
        "security_test_criteria": "No unauthorized dispatch",
    })
    with pytest.raises(ValueError, match="without evidence"):
        module.validate(doc)
    item["license_review"] = "PASS"
    item["hardware_review"] = "NOT_APPLICABLE"
    module.validate(doc)
