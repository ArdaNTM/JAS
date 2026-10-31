"""Windows owner-trust ACL and DPAPI helpers (not available to AURA agents).

Run under a *separate* operator-owned Windows account. DPAPI CurrentUser binds
the Ed25519 signing seed to that Windows logon. Both directory and file ACLs
are checked; an ACL failure prevents owner-service startup.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _powershell(script: str, *, path: Path) -> None:
    if os.name != "nt":
        raise RuntimeError("Windows owner storage is only supported on Windows")
    executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not executable.is_file():
        raise PermissionError("The trusted Windows PowerShell runtime is unavailable")
    env = dict(os.environ)
    env["AURA_OWNER_ACL_PATH"] = str(path)
    # GitHub Actions pwsh, and desktop PowerShell 7, can inject a PSModulePath
    # containing incompatible PowerShell 7 modules into powershell.exe 5.1.
    # That prevents Microsoft.PowerShell.Security (Get-Acl / Set-Acl) loading.
    # Use only the system-owned Windows PowerShell 5.1 module directory.
    module_root = executable.parent / "Modules"
    if not module_root.is_dir():
        raise PermissionError("Trusted Windows PowerShell security modules unavailable")
    env["PSModulePath"] = str(module_root)
    process = subprocess.run(
        [str(executable), "-NoProfile", "-NonInteractive", "-Command", script],
        env=env, capture_output=True, text=True, timeout=15, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if process.returncode != 0:
        raise PermissionError("Owner state NTFS ACL is not private or could not be validated")


_CHECK_ACL = r"""
$ErrorActionPreference = 'Stop'
try {
    $p = $env:AURA_OWNER_ACL_PATH
    $entry = Get-Item -LiteralPath $p -Force
    if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { exit 10 }
    $acl = Get-Acl -LiteralPath $p
    $self = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $valid = @($self, 'S-1-5-18', 'S-1-5-32-544')
    $owner = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if ($owner -ne $self -and $owner -ne 'S-1-5-32-544') { exit 11 }
    if (-not $acl.AreAccessRulesProtected) { exit 12 }
    foreach ($ace in $acl.Access) {
        $sid = $ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
        if ($sid -notin $valid -or $ace.IsInherited) { exit 13 }
    }
} catch { exit 14 }
"""


_HARDEN = r"""
$ErrorActionPreference = 'Stop'
try {
    $p = $env:AURA_OWNER_ACL_PATH
    $entry = Get-Item -LiteralPath $p -Force
    if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { exit 10 }
    $me = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = Get-Acl -LiteralPath $p
    $owner = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if ($owner -ne $me.Value -and $owner -ne 'S-1-5-32-544') { exit 11 }

    # Build an explicit DACL using Windows icacls rather than constructing a
    # blank DirectorySecurity/FileSecurity object (Set-Acl of an empty security
    # descriptor fails on some Windows installations). The production caller
    # already required the PARENT DACL to be private before reaching here.
    $tool = Join-Path $env:SystemRoot 'System32\icacls.exe'
    if (-not (Test-Path -LiteralPath $tool)) { exit 14 }
    & $tool $p /reset | Out-Null
    if ($LASTEXITCODE -ne 0) { exit 14 }
    & $tool $p /inheritance:r | Out-Null
    if ($LASTEXITCODE -ne 0) { exit 14 }
    $permissions = if ($entry.PSIsContainer) { '(OI)(CI)F' } else { 'F' }
    foreach ($sid in @($me.Value, 'S-1-5-18', 'S-1-5-32-544')) {
        $ace = '*' + $sid + ':' + $permissions
        & $tool $p /grant:r $ace | Out-Null
        if ($LASTEXITCODE -ne 0) { exit 14 }
    }
} catch { exit 14 }
"""


def require_private_acl(path: Path) -> None:
    """Fail closed if owner file/directory is inherited, shared or reparse-point."""
    if os.name != "nt":
        return
    item = Path(path)
    if not item.is_absolute() or not item.exists() or item.is_symlink():
        raise PermissionError("Owner storage path must exist and be absolute")
    _powershell(_CHECK_ACL, path=item)


def harden_private_acl(path: Path) -> None:
    """Explicit provisioning only; never weaken the parent container ACL."""
    if os.name != "nt":
        return
    item = Path(path)
    if not item.is_absolute() or not item.exists() or item.is_symlink():
        raise PermissionError("Invalid owner storage path")
    require_private_acl(item.parent)
    _powershell(_HARDEN, path=item)
    require_private_acl(item)


def load_owner_seed_dpapi(path: Path) -> Ed25519PrivateKey:
    """Load a user-scoped encrypted 32-byte seed directly via CryptUnprotectData.

    No PEM fallback is allowed on Windows. Private material is never printed
    or placed on a command line. Only the independent owner service may call.
    """
    if os.name != "nt":
        raise PermissionError("DPAPI owner key requires Windows")
    require_private_acl(path)
    raw = Path(path).read_bytes()
    if not 40 <= len(raw) <= 8192:
        raise PermissionError("Invalid encrypted Ed25519 owner key")

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]

    data = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    encrypted = DataBlob(len(raw), ctypes.cast(data, ctypes.c_void_p))
    decrypted = DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not crypt32.CryptUnprotectData(
        ctypes.byref(encrypted), None, None, None, None, 1,
        ctypes.byref(decrypted),
    ):
        raise PermissionError("Owner DPAPI decryption denied (wrong Windows identity?)")
    try:
        seed = ctypes.string_at(decrypted.pbData, decrypted.cbData)
    finally:
        kernel32.LocalFree(decrypted.pbData)
    if len(seed) != 32:
        raise PermissionError("Owner Ed25519 key seed is invalid")
    return Ed25519PrivateKey.from_private_bytes(seed)
