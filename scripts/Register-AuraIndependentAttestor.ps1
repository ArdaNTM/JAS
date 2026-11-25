# Register only from the independently provisioned attestor Windows account.
# An interactive logon task does not run before that account logs on.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$CoreIdentity,
    [Parameter(Mandatory)][string]$TrustedPython,
    [Parameter(Mandatory)][string]$TrustedWorkingDirectory,
    [string]$EvolutionRoot = 'D:\AURA\Evolution',
    [string]$PrivateKey = (Join-Path $env:LOCALAPPDATA 'AURA\AttestorKeys\sandbox-attestor.pem'),
    [switch]$StartNow
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:OS -ne 'Windows_NT') { throw 'Windows required' }
$current = [Security.Principal.WindowsIdentity]::GetCurrent()
$coreSid = if ($CoreIdentity -match '^S-1-') {
    [Security.Principal.SecurityIdentifier]::new($CoreIdentity)
} else {
    [Security.Principal.NTAccount]::new($CoreIdentity).Translate([Security.Principal.SecurityIdentifier])
}
if ($coreSid.Value -eq $current.User.Value -or $current.IsSystem) {
    throw 'Attestor must be a separate non-SYSTEM Windows account'
}
foreach ($path in @($TrustedPython, $TrustedWorkingDirectory, $EvolutionRoot, $PrivateKey)) {
    if (-not [IO.Path]::IsPathRooted($path) -or $path.Contains('"') -or $path -match '[\r\n]') {
        throw 'Absolute local paths without quotes or control characters required'
    }
    $item = Get-Item -LiteralPath $path -Force
    while ($null -ne $item) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'Reparse points are forbidden in attestor deployment paths'
        }
        $item = if ($item -is [IO.FileInfo]) { $item.Directory } else { $item.Parent }
    }
}
if (-not (Test-Path -LiteralPath $TrustedPython -PathType Leaf) -or
    -not (Test-Path -LiteralPath $TrustedWorkingDirectory -PathType Container)) {
    throw 'Independently deployed attestor release is missing'
}
# The operator must install the pinned release into a directory not writable
# by Core, including the Python installation, dependencies and imported code.
# Never copy or expose the signer to the Core checkout or process.
$TrustedPython = (Resolve-Path -LiteralPath $TrustedPython).Path
$TrustedWorkingDirectory = (Resolve-Path -LiteralPath $TrustedWorkingDirectory).Path
$EvolutionRoot = (Resolve-Path -LiteralPath $EvolutionRoot).Path
$PrivateKey = (Resolve-Path -LiteralPath $PrivateKey).Path
foreach ($setting in @('AURA_STORAGE_MODE','AURA_EVOLUTION_AUTO_ACTIVATE','AURA_EVOLUTION_DELEGATION_KEY_SHA256')) {
    $value = [Environment]::GetEnvironmentVariable($setting, 'User')
    if ([string]::IsNullOrWhiteSpace($value)) { throw "Missing independent account setting: $setting" }
    [Environment]::SetEnvironmentVariable($setting, $value, 'Process')
}
if ($env:AURA_STORAGE_MODE -ne 'local' -or $env:AURA_EVOLUTION_AUTO_ACTIVATE -ne '1') {
    throw 'Independent account has not enabled local delegated activation'
}
$check = @'
import sys
from pathlib import Path
from aura_core.evolution.attestor_worker import _load_signer
from aura_core.evolution.activation_delegation import ActivationDelegationVerifier
from aura_core.evolution.external_staging import EvolutionWorkspace
from cryptography.hazmat.primitives import serialization
import hashlib
key = _load_signer(Path(sys.argv[2]))
grant = ActivationDelegationVerifier(EvolutionWorkspace(Path(sys.argv[1]))).verified_grant()
raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
if grant is None or hashlib.sha256(raw).hexdigest() != grant["attestor_key_sha256"]:
    raise PermissionError("Independent attestor identity or Owner grant invalid")
'@
Push-Location -LiteralPath $TrustedWorkingDirectory
try {
    & $TrustedPython -I -B -c $check $EvolutionRoot $PrivateKey
    if ($LASTEXITCODE -ne 0) { throw 'Independent signer validation failed' }
} finally { Pop-Location }
$sha = [Security.Cryptography.SHA256]::Create()
try {
    $digest = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($EvolutionRoot.ToLowerInvariant()))).Replace('-', '').Substring(0, 16)
} finally { $sha.Dispose() }
$name = 'AURA-Independent-Attestor-' + $digest
$existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if ($null -ne $existing) {
    $existingUser = $existing.Principal.UserId
    $existingSid = if ($existingUser -match '^S-1-') { $existingUser } else {
        [Security.Principal.NTAccount]::new($existingUser).Translate([Security.Principal.SecurityIdentifier]).Value
    }
    if ($existingSid -ne $current.User.Value) { throw 'Existing task belongs to another identity' }
}
$args = '-I -B -m aura_core.evolution.attestor_worker --watch --poll-seconds 60 --evolution-root "' + $EvolutionRoot + '" --private-key "' + $PrivateKey + '"'
$action = New-ScheduledTaskAction -Execute $TrustedPython -Argument $args -WorkingDirectory $TrustedWorkingDirectory
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $current.Name
$principal = New-ScheduledTaskPrincipal -UserId $current.Name -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Independent AURA attestation; no Core-owned signer' -Force | Out-Null
if ($StartNow) { Start-ScheduledTask -TaskName $name }
Write-Host "Registered independent task: $name (interactive logon; restart on failure)"
