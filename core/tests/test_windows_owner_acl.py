"""On real Windows, unexpected NTFS identities must still fail closed.

No monkeypatch of os.name or require_private_acl: security tests exercise
genuine Windows ACL checks and native ACE mutation on throwaway pytest paths.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

from aura_core.evolution.windows_owner_storage import (
    harden_private_acl, require_private_acl,
)


pytestmark = pytest.mark.skipif(os.name != "nt", reason="NTFS ACL acceptance only runs on Windows")


def _add_untrusted_ace(path: Path) -> None:
    """Inject a real, explicit Everyone ACE into test-only NTFS storage.

    Use the same native Windows ACL utility as production provisioning: some
    Windows configurations reject Set-Acl with a modified .NET ACL object.
    Do not weaken or mock the production ACL validation.
    """
    tool = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "icacls.exe"
    if not tool.is_file():
        pytest.fail("Trusted Windows icacls.exe unavailable")
    result = subprocess.run(
        [str(tool), str(path), "/grant", "*S-1-1-0:R"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        pytest.fail(
            f"Cannot inject test-only Everyone ACE (exit={result.returncode}, "
            f"stdout={result.stdout[-500:]!r}, stderr={result.stderr[-500:]!r})"
        )


def test_windows_acl_rejects_untrusted_explicit_ace(owner_private_dir):
    private = owner_private_dir / "private-receipts.sqlite"
    private.write_bytes(b"")
    harden_private_acl(private)
    require_private_acl(private)
    try:
        _add_untrusted_ace(private)
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
        _add_untrusted_ace(parent)
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
