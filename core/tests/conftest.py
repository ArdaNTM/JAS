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
        try:
            _powershell(_HARDEN, path=destination)
        except PermissionError as exc:
            # Diagnostic only; no production permission bypass. Re-run on the
            # same throwaway directory and reveal which native Windows step
            # failed, without printing any secret or private key.
            import subprocess
            ps = Path(os.environ.get("SystemRoot", r"C:\\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
            script = _HARDEN.replace(
                "catch { exit 14 }",
                "catch { Write-Output ('ERROR:' + $_.Exception.Message); exit 14 }",
            ).replace(
                "if ($LASTEXITCODE -ne 0) { exit 14 }",
                "if ($LASTEXITCODE -ne 0) { Write-Output ('ICACLS-EXIT:' + $LASTEXITCODE); exit 14 }",
            ).replace(
                "if ($owner -ne $me.Value -and $owner -ne 'S-1-5-32-544') { exit 11 }",
                "if ($owner -ne $me.Value -and $owner -ne 'S-1-5-32-544') { Write-Output 'OWNER-MISMATCH'; exit 11 }",
            )
            environment = os.environ.copy()
            environment["AURA_OWNER_ACL_PATH"] = str(destination)
            result = subprocess.run(
                [str(ps), "-NoProfile", "-NonInteractive", "-Command", script],
                env=environment, text=True, capture_output=True, timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            raise AssertionError(
                f"Windows test ACL fixture failed (exit={result.returncode}, "
                f"stdout={result.stdout[-1000:]!r}, stderr={result.stderr[-1000:]!r})"
            ) from exc
        require_private_acl(destination)
    return destination
