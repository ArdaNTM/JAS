# First-run only: execute interactively as the dedicated Windows Local Owner.
# Not invoked by AURA Core/agents. Refuses to overwrite existing identity state.
[CmdletBinding()]
param(
    [string]$TrustRoot = (Join-Path $env:LOCALAPPDATA 'AURA\OwnerTrust')
)
$ErrorActionPreference = 'Stop'
if (-not [IO.Path]::IsPathRooted($TrustRoot)) { throw 'Absolute trust root required' }
if (Test-Path -LiteralPath $TrustRoot) { throw 'Trust root already exists; refuse to rotate or overwrite keys' }
$parent = Split-Path -Parent $TrustRoot
if (-not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}
$ident = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $ident.User) { throw 'No authenticated Windows owner SID' }
function Protect-Acl([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'Reparse points are forbidden in owner state'
    }
    $previous = Get-Acl -LiteralPath $Path
    $ownerSid = $previous.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if ($ownerSid -ne $ident.User.Value -and $ownerSid -ne 'S-1-5-32-544') {
        throw 'Owner state cannot be reprovisioned for an unknown Windows identity'
    }

    # icacls builds a portable explicit DACL without replacing the entire
    # Windows security descriptor with a blank DirectorySecurity/FileSecurity.
    $icacls = Join-Path $env:SystemRoot 'System32\icacls.exe'
    if (-not (Test-Path -LiteralPath $icacls)) {
        throw 'Native NTFS access control tool unavailable'
    }
    & $icacls $Path /reset | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'ACL reset failed' }
    & $icacls $Path /inheritance:r | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Disabling ACL inheritance failed' }
    $rights = if ($item.PSIsContainer) { '(OI)(CI)F' } else { 'F' }
    foreach ($sid in @($ident.User.Value, 'S-1-5-18', 'S-1-5-32-544')) {
        $access = '*' + $sid + ':' + $rights
        & $icacls $Path /grant:r $access | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Owner ACL grant failed' }
    }
    $verified = Get-Acl -LiteralPath $Path
    if (-not $verified.AreAccessRulesProtected) {
        throw 'Owner ACL inheritance protection missing'
    }
    foreach ($ace in $verified.Access) {
        $sid = $ace.IdentityReference.Translate(
            [Security.Principal.SecurityIdentifier]).Value
        if ($sid -notin @($ident.User.Value, 'S-1-5-18', 'S-1-5-32-544') -or
            $ace.IsInherited) {
            throw 'Unexpected principal or inherited ACE in owner state'
        }
    }
}
New-Item -ItemType Directory -Path $TrustRoot | Out-Null
Protect-Acl $TrustRoot
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$seed = New-Object byte[] 32
$token = New-Object byte[] 32
try {
    $rng.GetBytes($seed)
    $rng.GetBytes($token)
    Add-Type -AssemblyName System.Security
    $cipher = [Security.Cryptography.ProtectedData]::Protect(
        $seed, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser
    )
    $tokenHex = [BitConverter]::ToString($token).Replace('-', '').ToLowerInvariant()
    $files = @{
        'owner-receipt-key.dpapi' = $cipher
        'bootstrap-token.txt' = [Text.Encoding]::ASCII.GetBytes($tokenHex)
        'approvals.sqlite' = [byte[]]@()
        'challenges.sqlite' = [byte[]]@()
        'receipt-ledger.sqlite' = [byte[]]@()
    }
    foreach ($name in $files.Keys) {
        $p = Join-Path $TrustRoot $name
        [IO.File]::WriteAllBytes($p, [byte[]]$files[$name])
        Protect-Acl $p
    }
} finally {
    [Array]::Clear($seed, 0, $seed.Length)
    [Array]::Clear($token, 0, $token.Length)
    $rng.Dispose()
}
Write-Host 'Owner files provisioned with explicit NTFS ACLs and user-scoped DPAPI.'
Write-Host "Trust root: $TrustRoot"
Write-Host 'Owner public credential is not created until verified Windows Hello enrollment.'
Write-Host 'Use bootstrap-token.txt only for the first 90-second ceremony; delete it after enrollment.'
Write-Host 'Different Windows service users require separately provisioned ACL-protected state.'
