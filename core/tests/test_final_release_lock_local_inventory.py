"""Local editable-install metadata must not invalidate a pinned release inventory."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import importlib.util

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "aura_release_lock_local_inventory", ROOT / "core/scripts/generate_final_lock.py",
)
assert spec is not None and spec.loader is not None
lock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lock)


def test_release_inventory_excludes_only_untracked_generated_metadata(tmp_path, monkeypatch):
    root = tmp_path
    target = root / "core" / "src" / "aura_core"
    target.mkdir(parents=True)
    trusted = target / "kernel.py"
    trusted.write_text("SAFE = True\n", encoding="utf-8")
    editable = root / "core" / "src" / "aura_core.egg-info"
    editable.mkdir()
    (editable / "PKG-INFO").write_text("Local edit build\n", encoding="utf-8")
    (target / "__pycache__").mkdir()
    (target / "__pycache__" / "kernel.cpython-313.pyc").write_bytes(b"temporary")

    monkeypatch.setattr(lock, "ROOT", root)
    def tracked_git(argv, *, cwd):
        assert argv == ["git", "ls-files", "--cached", "-z"]
        assert cwd == root
        return b"core/src/aura_core/kernel.py\0"
    monkeypatch.setattr(lock.subprocess, "check_output", tracked_git)
    assert lock.files_to_hash() == [trusted]

    rogue = target / "untracked.py"
    rogue.write_text("def execute(): pass\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Untracked executable"):
        lock.files_to_hash()
    rogue.unlink()
    assert lock.files_to_hash() == [trusted]
