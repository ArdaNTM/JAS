"""Real ACL-backed temporary owner storage for Windows security regressions.

The fixture intentionally provisions one child inside pytest's temp directory.
It does NOT change TEMP, pytest's shared parent, the logged-in Windows user's
profile, or production authorization. Only tests may use the low-level ACL
writer to initialize an otherwise inherited, newly-created directory.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def owner_private_dir(tmp_path: Path) -> Path:
    destination = tmp_path / "isolated-owner-state"
    destination.mkdir(mode=0o700)
    if os.name == "nt":
        from aura_core.evolution.windows_owner_storage import (
            _HARDEN, _powershell, require_private_acl,
        )

        # Test fixture bootstrap: the production harden_private_acl method
        # correctly rejects an inherited parent, which pytest tmp_path has.
        # Apply the real explicit protected DACL only to this test-owned leaf.
        _powershell(_HARDEN, path=destination)
        require_private_acl(destination)
    return destination
