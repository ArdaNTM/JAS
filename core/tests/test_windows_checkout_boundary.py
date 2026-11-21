"""Windows case-insensitive checkout/TEMP containment regression.

The PR #64 Owner/Attestor validators are sealed. This suite checks the
platform path semantics they rely on without weakening their ACL controls.
"""
from __future__ import annotations

import ntpath
import os
import sys
import tempfile
from pathlib import Path, PureWindowsPath

import pytest


def test_windows_pathlib_casefold_and_component_boundary():
    checkout = PureWindowsPath(r"D:\AURA\JAS")
    assert PureWindowsPath(r"d:\aura\jas\core\owner.sqlite3").is_relative_to(checkout)
    assert not PureWindowsPath(r"D:\AURA\JAS-other\owner.sqlite3").is_relative_to(checkout)
    assert not PureWindowsPath(r"C:\Users\Owner\AppData\Local\Temp\owner.sqlite3").is_relative_to(checkout)
    assert ntpath.normcase(ntpath.commonpath([
        r"D:\AURA\JAS", r"d:\aura\jas\core\owner.sqlite3"
    ])) == ntpath.normcase(r"D:\AURA\JAS")
    with pytest.raises(ValueError):
        ntpath.commonpath([r"D:\AURA\JAS", r"C:\Temp\owner.sqlite3"])


@pytest.mark.skipif(sys.platform != "win32", reason="Windows filesystem path semantics")
def test_actual_windows_owner_checkout_boundary_and_temp(tmp_path):
    # The sealed Owner modules use Path.resolve().is_relative_to; on NT
    # WindowsPath compares case-insensitively and resolves junctions.
    root = Path(__file__).resolve().parents[2]
    nested = root / "core" / "tests" / "_nonexistent_owner_record"
    assert nested.resolve().is_relative_to(root.resolve())
    case_variant = Path(str(nested).swapcase())
    assert case_variant.resolve().is_relative_to(root.resolve())

    # This must use a checkout-external --basetemp. Never whitelist an unsafe
    # TEMP inside the repository or bypass require_private_acl().
    external = tmp_path.resolve()
    assert not external.is_relative_to(root.resolve())
    assert not (external / "owner.sqlite3").resolve().is_relative_to(root.resolve())
