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
    assert len(tests) == 64 and len(tests) == len(set(tests))
    assert missing == ()  # Every original B2-Env focus test is now present.
    assert "tests/test_subsystem_pack3.py" in tests
    assert "tests/test_subsystem_pack4.py" in tests
    assert b2.main(["--repo-root", str(ROOT), "--list-only"]) == 0
    out = capsys.readouterr().out
    assert "71 TESTING" in out
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
        assert present
        union.update(ids)
    assert union == set(groups["B2_env_ids"])
