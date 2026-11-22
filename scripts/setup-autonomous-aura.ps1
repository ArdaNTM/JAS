# One-time interactive Windows Owner + attestor bootstrap.
# Owner Windows Hello presence is required; NO silent WebAuthn bypass.
[CmdletBinding()]
param(
    [string]$EvolutionRoot = 'D:\AURA\Evolution',
    [string]$DockerImage = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($env:OS -ne 'Windows_NT') {
    throw 'Windows 11 required'
}
if (-not [IO.Path]::IsPathRooted($EvolutionRoot)) {
    throw 'External evolution root must be absolute'
}
$Root = Split-Path -Parent $PSScriptRoot
$Core = Join-Path $Root 'core'
$Python = Join-Path $Core '.venv\Scripts\python.exe'
$Owner = Join-Path $EvolutionRoot 'owner'
$AttestorKeys = Join-Path $env:LOCALAPPDATA 'AURA\AttestorKeys'
$Private = Join-Path $AttestorKeys 'sandbox-attestor.pem'
$Public = Join-Path $EvolutionRoot 'trust\sandbox-attestor.pub.pem'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw 'Locked Python core venv unavailable; run uv sync --frozen inside core first'
}
if (-not (Test-Path -LiteralPath $EvolutionRoot -PathType Container)) {
    New-Item -ItemType Directory -Path $EvolutionRoot -Force | Out-Null
}
if ((Get-Item -LiteralPath $EvolutionRoot -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'Reparse point evolution roots are forbidden'
}
$env:AURA_STORAGE_MODE = 'local'
$env:AURA_EVOLUTION_ROOT = $EvolutionRoot

function Assert-PrivateAcl([string]$Path) {
    $test = 'import sys; from pathlib import Path; from aura_core.evolution.windows_owner_storage import require_private_acl; require_private_acl(Path(sys.argv[1]))'
    & $Python -c $test $Path
    if ($LASTEXITCODE -ne 0) { throw "Owner NTFS private ACL failed for $Path" }
}

function Harden-TrustDirectory([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'Refuse link/junction in attestor trust path'
    }
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $acl = Get-Acl -LiteralPath $Path
    $ownerSid = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if ($ownerSid -ne $sid -and $ownerSid -ne 'S-1-5-32-544') {
        throw 'Unknown owner for attestor trust directory'
    }
    $icacls = Join-Path $env:SystemRoot 'System32\icacls.exe'
    & $icacls $Path /inheritance:r | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot protect attestor ACL inheritance' }
    foreach ($allowedSid in @($sid, 'S-1-5-18', 'S-1-5-32-544')) {
        & $icacls $Path /grant:r ('*' + $allowedSid + ':(OI)(CI)F') | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Failed private attestor ACL' }
    }
    Assert-PrivateAcl $Path
}

# Reuse established DPAPI and real Windows Hello Owner trust bootstrap.
if (-not (Test-Path -LiteralPath $Owner)) {
    & (Join-Path $Root 'core\scripts\provision_windows_owner.ps1') -TrustRoot $Owner
    if (-not (Test-Path -LiteralPath $Owner)) { throw 'Owner trust bootstrap failed' }
}
Assert-PrivateAcl $Owner
Assert-PrivateAcl (Join-Path $Owner 'owner-receipt-key.dpapi')

$Passkey = Join-Path $Owner 'owner-passkey.json'
if (-not (Test-Path -LiteralPath $Passkey)) {
    $Bootstrap = Join-Path $Owner 'bootstrap-token.txt'
    Assert-PrivateAcl $Bootstrap
    $PolicyDigest = (& $Python -c 'from aura_core.evolution.activation_delegation import SANDBOX_POLICY_SHA256; print(SANDBOX_POLICY_SHA256)').Trim()
    if ($LASTEXITCODE -ne 0 -or $PolicyDigest -notmatch '^[0-9a-f]{64}$') {
        throw 'Cannot derive trusted Owner policy digest'
    }
    if (Get-NetTCPConnection -State Listen -LocalPort 8766 -ErrorAction SilentlyContinue) {
        throw 'Owner enrollment port 8766 occupied; stop AURA Owner Review first'
    }
    $EnrollmentOut = Join-Path $EvolutionRoot 'owner-enrollment.stdout.log'
    $EnrollmentErr = Join-Path $EvolutionRoot 'owner-enrollment.stderr.log'
    $Enrollment = Start-Process -FilePath $Python -WorkingDirectory $Core -PassThru -WindowStyle Hidden `
        -ArgumentList @('scripts/enroll_local_owner.py', '--bootstrap-token-file', ('"' + $Bootstrap + '"'),
            '--owner-config-output', ('"' + $Passkey + '"'), '--policy-digest', $PolicyDigest) `
        -RedirectStandardOutput $EnrollmentOut -RedirectStandardError $EnrollmentErr
    try {
        Start-Sleep -Seconds 2
        if ($Enrollment.HasExited) { throw 'Windows Hello enrollment service did not start' }
        # Clipboard token is short-lived; no hash needs typing or manual generation.
        Set-Clipboard -Value ([IO.File]::ReadAllText($Bootstrap).Trim())
        Write-Host 'Windows Hello kaydı için tarayıcı açılıyor. Ctrl+V ile geçici tokenı yapıştırıp Enroll seçin.'
        Start-Process 'http://localhost:8766/'
        $deadline = (Get-Date).AddMinutes(5)
        while (-not (Test-Path -LiteralPath $Passkey) -and (Get-Date) -lt $deadline) {
            Start-Sleep -Seconds 2
        }
        if (-not (Test-Path -LiteralPath $Passkey)) {
            throw 'Windows Hello owner enrollment was not completed'
        }
    }
    finally {
        cmd.exe /c "echo off | clip" | Out-Null
        Stop-Process -Id $Enrollment.Id -Force -ErrorAction SilentlyContinue
    }
    Assert-PrivateAcl $Passkey
    Remove-Item -LiteralPath $Bootstrap -Force
} else {
    Assert-PrivateAcl $Passkey
}

Harden-TrustDirectory $AttestorKeys
if (-not (Test-Path -LiteralPath $Private -PathType Leaf)) {
    if (Test-Path -LiteralPath $Public) {
        throw 'Attestor public key exists without private key; refuse implicit rotation'
    }
    & $Python -m aura_core.evolution.attestor_worker `
        --evolution-root $EvolutionRoot --provision-key-root $AttestorKeys
    if ($LASTEXITCODE -ne 0) { throw 'Independent attestor key provisioning failed' }
}
Assert-PrivateAcl $Private

$KeyInfo = @'
import hashlib, sys
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from aura_core.evolution.attestor_worker import _load_signer
key = _load_signer(Path(sys.argv[1]))
public = serialization.load_pem_public_key(Path(sys.argv[2]).read_bytes())
raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
other = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
if raw != other: raise PermissionError("Attestor public/private mismatch")
print(hashlib.sha256(raw).hexdigest())
'@
$AttestorPin = (& $Python -c $KeyInfo $Private $Public).Trim()
if ($LASTEXITCODE -ne 0 -or $AttestorPin -notmatch '^[0-9a-f]{64}$') {
    throw 'Attestor public/private fingerprint verification failed'
}

# Prefer a genuine local pinned OCI digest if Docker Desktop is running.
# When Docker is unavailable, signed policy is Windows-local-only (image=None).
if (-not $DockerImage) {
    $docker = Get-Command docker.exe -ErrorAction SilentlyContinue
    if ($docker) {
        $candidates = @(& $docker.Source image ls --format '{{.Repository}}@{{.Digest}}' 2>$null)
        foreach ($candidate in $candidates) {
            if ($candidate -match '^[A-Za-z0-9._/-]+@sha256:[a-f0-9]{64}$') {
                $DockerImage = $candidate
                break
            }
        }
    }
}
if ($DockerImage -and $DockerImage -notmatch '^[A-Za-z0-9._/-]+@sha256:[a-f0-9]{64}$') {
    throw 'Docker image must be a genuine digest-pinned reference'
}

$Delegation = Join-Path $Owner 'autonomous_delegation.json'
if (-not (Test-Path -LiteralPath $Delegation)) {
    $args = @(
        '-m', 'aura_core.evolution.owner_cli', 'sign-activation-delegation',
        '--owner-root', $Owner, '--categories',
        'windows_automation', 'local_memory', 'developer_tools',
        'filesystem', 'research', 'browser',
        '--attestor-key-sha256', $AttestorPin,
        '--attestor-runner-id', 'local_windows_operator',
        '--days', '365', '--max-tools', '16', '--min-score', '70',
        '--allow-local-windows-process', '--confirm-owner-authority'
    )
    if ($DockerImage) { $args += @('--image', $DockerImage) }
    & $Python @args
    if ($LASTEXITCODE -ne 0) { throw 'Owner delegation signing failed' }
}
Assert-PrivateAcl $Delegation
$Fingerprint = @'
import hashlib, sys
from pathlib import Path
from cryptography.hazmat.primitives import serialization
key = serialization.load_pem_public_key(Path(sys.argv[1]).read_bytes())
raw = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
print(hashlib.sha256(raw).hexdigest())
'@
$OwnerPin = (& $Python -c $Fingerprint (Join-Path $Owner 'autonomous_delegation.pub.pem')).Trim()
if ($LASTEXITCODE -ne 0 -or $OwnerPin -notmatch '^[0-9a-f]{64}$') {
    throw 'Owner public fingerprint derivation failed'
}

foreach ($setting in @{
    'AURA_STORAGE_MODE' = 'local'
    'AURA_EVOLUTION_ROOT' = $EvolutionRoot
    'AURA_EVOLUTION_AUTO_ACTIVATE' = '1'
    'AURA_EVOLUTION_DELEGATION_KEY_SHA256' = $OwnerPin
    'AURA_EVOLUTION_ATTESTOR_KEY_SHA256' = $AttestorPin
}.GetEnumerator()) {
    [Environment]::SetEnvironmentVariable($setting.Key, $setting.Value, 'User')
    [Environment]::SetEnvironmentVariable($setting.Key, $setting.Value, 'Process')
}
& $Python -m aura_core.evolution.activation_delegation --verify --evolution-root $EvolutionRoot
if ($LASTEXITCODE -ne 0) {
    [Environment]::SetEnvironmentVariable('AURA_EVOLUTION_AUTO_ACTIVATE', '0', 'User')
    throw 'Owner delegation signature/scope verification failed; activation disabled'
}
# An existing standing delegation is never silently replaced or broadened.
# Require precisely the requested signed scope before declaring success.
$ScopeCheck = @'
import sys
from pathlib import Path
from aura_core.evolution.activation_delegation import ActivationDelegationVerifier
from aura_core.evolution.external_staging import EvolutionWorkspace
g = ActivationDelegationVerifier(EvolutionWorkspace(Path(sys.argv[1]))).verified_grant()
required = {"windows_automation", "local_memory", "developer_tools", "filesystem", "research", "browser"}
if (g is None or g.get("allow_local_windows_process") is not True
    or not required.issubset(set(g["categories"]))
    or g["attestor_key_sha256"] != sys.argv[2]):
    raise SystemExit(4)
'@
& $Python -c $ScopeCheck $EvolutionRoot $AttestorPin
if ($LASTEXITCODE -ne 0) {
    [Environment]::SetEnvironmentVariable('AURA_EVOLUTION_AUTO_ACTIVATE', '0', 'User')
    throw 'Standing Owner delegation does not explicitly permit requested local Windows scope; revoke and re-enroll'
}
Write-Host 'AURA Owner/attestor kurulumu tamamlandı; Owner ve imzalı politika doğrulandı.'
Write-Warning 'Windows Job Object aynı kullanıcıdaki DPAPI, dosya ve ağ erişimini yalıtmaz; yerel MCP yalnızca açıkça Owner-onaylı daha zayıf moddur.'
