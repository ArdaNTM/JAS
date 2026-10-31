from __future__ import annotations

import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1] / "scripts"


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_osworld_release_manifest_must_be_pinned():
    lab = load("osworld_lab", "osworld_v2_lab.py")
    lab.validate_manifest(lab.MANIFEST)
    for field in ("release", "code_tag", "task_assets_tag", "task_classes_tag", "website_tag"):
        changed = dict(lab.MANIFEST, **{field: "main"})
        with pytest.raises(ValueError):
            lab.validate_manifest(changed)
    with pytest.raises(ValueError):
        lab.validate_manifest(dict(lab.MANIFEST, environment="owner_desktop"))
    assert lab.main([]) == 0


def test_hardware_acceptance_never_claims_automatic_verification(capsys):
    test = load("hardware_acceptance", "hardware_stage_c_acceptance.py")
    assert test.main([]) == 0
    result = capsys.readouterr().out
    assert '"hardware_verified": false' in result
    assert '"manual_review_required": true' in result
