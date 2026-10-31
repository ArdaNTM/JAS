"""On real Windows, unexpected NTFS identities must still fail closed.

No monkeypatch of os.name or require_private_acl: security tests exercise
genuine PowerShell Get-Acl and Set-Acl behavior on throwaway pytest paths.
"""
from __future__ import annotations

import os

import pytest

from aura_core.evolution.windows_owner_storage import (
    _powershell, harden_private_acl, require_private_acl,
)


pytestmark = pytest.mark.skipif(os.name != "nt", reason="NTFS ACL acceptance only runs on Windows")


_ADD_UNTRUSTED_ACE = r"""
$ErrorActionPreference = 'Stop'
try {
    $p = $env:AURA_OWNER_ACL_PATH
    $acl = Get-Acl -LiteralPath $p
    $rule = [Security.AccessControl.FileSystemAccessRule]::new(
        [Security.Principal.SecurityIdentifier]::new('S-1-1-0'),
        [Security.AccessControl.FileSystemRights]::ReadAndExecute,
        [Security.AccessControl.InheritanceFlags]::None,
        [Security.AccessControl.PropagationFlags]::None,
        [Security.AccessControl.AccessControlType]::Allow
    )
    $acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $p -AclObject $acl
} catch { exit 14 }
"""


def test_windows_acl_rejects_untrusted_explicit_ace(owner_private_dir):
    private = owner_private_dir / "private-receipts.sqlite"
    private.write_bytes(b"")
    harden_private_acl(private)
    require_private_acl(private)
    try:
        _powershell(_ADD_UNTRUSTED_ACE, path=private)
        with pytest.raises(PermissionError, match="NTFS ACL"):
            require_private_acl(private)
    finally:
        harden_private_acl(private)
    require_private_acl(private)


def test_windows_acl_refuses_hardening_under_untrusted_parent(owner_private_dir):
    parent = owner_private_dir / "untrusted-parent"
    parent.mkdir()
    harden_private_acl(parent)
    child = parent / "child"
    child.mkdir()
    try:
        _powershell(_ADD_UNTRUSTED_ACE, path=parent)
        with pytest.raises(PermissionError, match="NTFS ACL"):
            harden_private_acl(child)
    finally:
        # Own test-only state is repaired; production code remains fail-closed.
        harden_private_acl(parent)
    harden_private_acl(child)
    require_private_acl(child)


def test_windows_acl_requires_file_protection(owner_private_dir):
    receipt = owner_private_dir / "signed-receipt.sqlite"
    receipt.write_bytes(b"")
    # A file created in a private directory still inherits ACEs. The
    # provider must explicitly protect the file DACL before use.
    with pytest.raises(PermissionError, match="NTFS ACL"):
        require_private_acl(receipt)
    harden_private_acl(receipt)
    require_private_acl(receipt)
