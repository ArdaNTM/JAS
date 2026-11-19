"""B2 post-merge track integrity and safe read-only checklist discovery."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "aura_b2_postmerge", ROOT / "core/scripts/b2_postmerge_check.py")
assert spec is not None and spec.loader is not None
b2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b2)


def test_readonly_postmerge_focus_inventory_and_unverified_owner_requirements(capsys):
    tracker, groups = b2.load_b2(ROOT)
    tests, missing = b2.focused_tests(ROOT, tracker, groups)
    assert len(groups["B2_owner_ids"]) == 17
    assert len(groups["B2_env_ids"]) == 71
    assert len(tests) == 50 and len(tests) == len(set(tests))
    assert missing == ()  # Every original B2-Env focus test is now present.
    assert "tests/test_subsystem_pack3.py" not in tests  # Simulation-v1 accepted; never physical proof.
    assert "tests/test_subsystem_pack4.py" in tests
    assert b2.main(["--repo-root", str(ROOT), "--list-only"]) == 0
    out = capsys.readouterr().out
    assert "52 TESTING" in out
    assert "B2 hardware/Owner evidence NOT evaluated" in out


def test_b2_source_and_test_list_cannot_be_spoofed_or_escape_scope():
    tracker, groups = b2.load_b2(ROOT)
    forged = copy.deepcopy(tracker)
    one = groups["B2_env_ids"][0]
    forged["features"][one - 1]["test_commands"][0] = "cd core && uv run pytest -q tests/../../secret.py"
    with pytest.raises(ValueError):
        b2.focused_tests(ROOT, forged, groups)
    forged = copy.deepcopy(tracker)
    forged["features"][one - 1]["test_commands"][0] = (
        "cd core && uv run pytest -q tests/../../secret.py")
    with pytest.raises(ValueError):
        b2.focused_tests(ROOT, forged, groups)


def test_list_only_rejects_invalid_ubuntu_port_without_live_probe():
    with pytest.raises(SystemExit):
        b2.main(["--list-only", "--ubuntu-port", "0"])


def test_three_way_test_inventory_has_no_missing_sources_and_is_not_hardware_acceptance():
    tracker, groups = b2.load_b2(ROOT)
    union = set()
    for key, count in (("windows_local", 57), ("hyperv_docker", 7),
                       ("external_hardware_simulation", 7)):
        ids = groups["B2_env_validation_groups"][key]
        assert len(ids) == count
        present, missing = b2.focused_tests(ROOT, tracker, groups, target_ids=ids)
        assert missing == ()
        if key == "external_hardware_simulation":
            assert present == ()  # All 7 are simulation-v1, not hardware acceptance.
        else:
            assert present
        union.update(ids)
    assert union == set(groups["B2_env_ids"])


def test_scoped_pytest_json_evidence_stays_unsigned_and_fail_closed(tmp_path, monkeypatch):
    from types import SimpleNamespace

    tracker, groups = b2.load_b2(ROOT)
    outstanding = b2.pending_env_ids(tracker, groups)
    assert len(outstanding) == 52
    assert not set(outstanding) & b2.V1_ACCEPTED
    assert not set(outstanding) & set(
        groups["B2_env_validation_groups"]["external_hardware_simulation"]
    )

    monkeypatch.setattr(
        b2.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout="2 passed in 0.03s", stderr=""
        ),
    )
    output = tmp_path / "real-test-record.json"
    kwargs = dict(
        repo=ROOT,
        paths=("tests/test_feature_tracker_validation.py",),
        group="windows_local",
        feature_ids=[1],
        output=output,
        head="a" * 40,
    )
    assert b2.run_pytest_evidence(**kwargs, baseline_ok=True)
    report = b2.json.loads(output.read_text("utf-8"))
    assert report["result"] == "PASS_SOFTWARE_REGRESSION_ONLY"
    assert report["pytest_exit_code"] == 0
    assert report["is_signed"] is False
    assert report["hardware_verified"] is False
    assert report["owner_authorization_granted"] is False
    assert report["production_acceptance"] is False
    assert report["focused_test_files"][0]["sha256"]
    assert not b2.run_pytest_evidence(**kwargs, baseline_ok=False)
    assert b2.json.loads(output.read_text("utf-8"))["result"] == "BLOCKED"

    with pytest.raises(ValueError, match="outside the checkout"):
        b2.run_pytest_evidence(**{**kwargs, "output": ROOT / "core" / "forbidden.json"},
                              baseline_ok=True)


def test_scoped_json_report_requires_explicit_pytest_flags():
    with pytest.raises(SystemExit):
        b2.main(["--list-only", "--run-pytest"])
    with pytest.raises(SystemExit):
        b2.main(["--list-only", "--evidence-out", "report.json"])
