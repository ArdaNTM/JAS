#requires -Version 5.1
<#
F2.7 operator-only *inactive* F2.6 runtime candidate promotion.
Verifies exact Work candidate and promotes into a protected versioned bin child.
Never installs/starts SCM, enables accounts, provisions keys or writes service.json.
Read and review this script from an independently verified pinned Git commit.
#>
[CmdletBinding()]
param(
    [switch]$Promote,
    [switch]$SelfTest,
    [switch]$CleanupStale,
    [string]$StaleStageName,
    [string]$Source = 'D:\AURA\JAS\artifacts\aura-f26-runtime-38c42d1',
    [string]$TrustRoot = 'D:\AURA\Trust\DockerBroker'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ExpectedInventorySha = 'cb897595b79b9d2599ed90a12a60383ea9abd9b50a8eebe05dd929f094dd88a7'
$ExpectedProvenanceSha = 'dcba98548770f7610ce00313aa246179d7c2e00e2159182b71b584e35bfa0a0a'
$ExpectedScriptsSha = '31c6efd24ad3bf2c193a2a6c8b6d36a59fe4231df5f2fcba2e7be0a2d12869f0'
$AdminSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
$SystemSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')

function Assert-True([bool]$Condition, [string]$Reason) {
    if (-not $Condition) { throw "STOP: $Reason" }
}
function Assert-Relative([string]$Path) {
    Assert-True (-not [string]::IsNullOrWhiteSpace($Path)) 'Empty runtime filename'
    Assert-True ($Path -notmatch '(^[\\/]|^[A-Za-z]:|:|[<>|?*]|[\x00-\x1f])') 'Unsafe runtime filename'
    foreach ($Part in $Path.Replace('\', '/').Split('/')) {
        Assert-True ($Part -notin @('','.','..') -and
            -not $Part.EndsWith('.') -and -not $Part.EndsWith(' ')) 'Traversal/ambiguous filename'
    }
}
function Assert-NoLink([string]$Path) {
    $It = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    Assert-True (($It.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) "Reparse point: $Path"
}
function Assert-Sha([string]$Path, [string]$Expected) {
    Assert-True ($Expected -cmatch '^[0-9a-f]{64}$') 'Invalid SHA pin'
    Assert-NoLink $Path
    $Actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    Assert-True ($Actual -ceq $Expected) "SHA-256 mismatch: $Path"
}
function New-ProtectedAcl([bool]$Directory, [string]$BrokerSid) {
    $Acl = if ($Directory) {
        [Security.AccessControl.DirectorySecurity]::new()
    } else {
        [Security.AccessControl.FileSecurity]::new()
    }
    $Acl.SetAccessRuleProtection($true, $false)
    $Acl.SetOwner($AdminSid)
    $Inheritance = if ($Directory) {
        [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
    } else {
        [Security.AccessControl.InheritanceFlags]::None
    }
    foreach ($Id in @(
        [PSCustomObject]@{ Sid = $SystemSid; Right = [Security.AccessControl.FileSystemRights]::FullControl },
        [PSCustomObject]@{ Sid = $AdminSid; Right = [Security.AccessControl.FileSystemRights]::FullControl },
        [PSCustomObject]@{ Sid = [Security.Principal.SecurityIdentifier]::new($BrokerSid); Right = [Security.AccessControl.FileSystemRights]::ReadAndExecute }
    )) {
        $Acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            $Id.Sid, $Id.Right, $Inheritance,
            [Security.AccessControl.PropagationFlags]::None,
            [Security.AccessControl.AccessControlType]::Allow
        ))
    }
    return $Acl
}
function Test-BrokerReadExecuteOnly([int]$Rights) {
    # NTFS/.NET can add SYNCHRONIZE to FileSystemRights.ReadAndExecute
    # when the ACL is materialized. It does NOT grant write/delete/admin.
    $ReadExecute = [int][Security.AccessControl.FileSystemRights]::ReadAndExecute
    $Synchronize = [int][Security.AccessControl.FileSystemRights]::Synchronize
    $Allowed = $ReadExecute -bor $Synchronize
    return ((($Rights -band (-bnot $Allowed)) -eq 0) -and
            (($Rights -band $ReadExecute) -eq $ReadExecute))
}
function Assert-SealedAcl([string]$Path, [string]$BrokerSid) {
    Assert-NoLink $Path
    $Acl = Get-Acl -LiteralPath $Path -ErrorAction Stop
    Assert-True $Acl.AreAccessRulesProtected "Inherited ACL: $Path"
    Assert-True ($Acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ceq $AdminSid.Value) "Owner mismatch: $Path"
    $Expected = @($SystemSid.Value, $AdminSid.Value, $BrokerSid)
    $Saw = [collections.generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($Ace in $Acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
        $Sid = $Ace.IdentityReference.Value
        Assert-True ($Ace.AccessControlType -eq 'Allow' -and -not $Ace.IsInherited -and
            $Sid -in $Expected -and $Saw.Add($Sid)) "Untrusted or duplicate ACE: $Path ($Sid)"
        $Rights = [int]$Ace.FileSystemRights
        if ($Sid -ceq $BrokerSid) {
            Assert-True (Test-BrokerReadExecuteOnly $Rights) "Broker has unexpected rights: $Path (actual=$Rights)"
        } else {
            Assert-True (($Rights -band [int][Security.AccessControl.FileSystemRights]::FullControl) -eq
                [int][Security.AccessControl.FileSystemRights]::FullControl) "SYSTEM/Admin not full: $Path"
        }
    }
    Assert-True ($Saw.Count -eq 3) "Missing ACL principal: $Path"
}
function Read-Inventory([string]$Path) {
    $Parsed = ConvertFrom-Json -InputObject (Get-Content -LiteralPath $Path -Raw -Encoding UTF8)
    if ($Parsed -is [array]) { return $Parsed }
    if ($null -ne $Parsed -and $null -ne $Parsed.PSObject.Properties['files'] -and
        $Parsed.files -is [array]) { return $Parsed.files }
    throw "STOP: Unknown runtime inventory schema"
}

if ($SelfTest) {
    foreach ($Bad in @('..\out', 'C:\x', 'a//b', 'a/./b', 'a\b\..\x')) {
        $Refused = $false
        try { Assert-Relative $Bad } catch { $Refused = $true }
        Assert-True $Refused "Traversal test failed: $Bad"
    }
    Assert-Relative 'aura_core/osworld/audit_broker_service.py'
    Assert-True ($ExpectedProvenanceSha.Length -eq 64 -and
        $ExpectedInventorySha.Length -eq 64 -and
        $ExpectedScriptsSha.Length -eq 64) 'Truncated inventory hash'
    $ReadExecute = [int][Security.AccessControl.FileSystemRights]::ReadAndExecute
    $Synchronize = [int][Security.AccessControl.FileSystemRights]::Synchronize
    $WithSync = $ReadExecute -bor $Synchronize
    Assert-True (Test-BrokerReadExecuteOnly $ReadExecute) 'ReadAndExecute must be allowed'
    Assert-True (Test-BrokerReadExecuteOnly $WithSync) 'ReadAndExecute + SYNCHRONIZE must be allowed'
    foreach ($Forbidden in @(
        [int][Security.AccessControl.FileSystemRights]::WriteData,
        [int][Security.AccessControl.FileSystemRights]::Delete,
        [int][Security.AccessControl.FileSystemRights]::ChangePermissions,
        [int][Security.AccessControl.FileSystemRights]::TakeOwnership
    )) {
        Assert-True (-not (Test-BrokerReadExecuteOnly ($WithSync -bor $Forbidden))) 'Broker elevated ACE must be refused'
    }
    Assert-True (-not (Test-BrokerReadExecuteOnly $Synchronize)) 'SYNCHRONIZE without RX is insufficient'
    Assert-True ('.f26-staging-4229b3b53b634532b5363fd70b883cfa' -cmatch '^\.f26-staging-[0-9a-f]{32}$') 'Staging name pattern'
    Assert-True ('..\unsafe' -cnotmatch '^\.f26-staging-[0-9a-f]{32}$') 'Path traversal staging name should fail'
    Write-Host 'PASS: F2.7 offline promotion self-test'
    exit 0
}

$Principal = [Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent())
Assert-True ($Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) 'Elevated independent operator required'
Assert-True (-not ($CleanupStale -and $Promote)) 'Cleanup and promotion must be separate commands'
Assert-True ($CleanupStale -or [string]::IsNullOrWhiteSpace($StaleStageName)) 'Stale stage name provided without explicit -CleanupStale'
Assert-True ($TrustRoot -ceq 'D:\AURA\Trust\DockerBroker') 'Unapproved trust root'
Assert-True ($Source -ceq 'D:\AURA\JAS\artifacts\aura-f26-runtime-38c42d1') 'Unapproved artifact root'
$Broker = Get-LocalUser -Name AuraDockerBroker -ErrorAction Stop
Assert-True (-not $Broker.Enabled) 'Broker must remain disabled'
Assert-True ($null -eq (Get-CimInstance Win32_Service -Filter "Name='AuraOSWorldAuditBroker'")) 'SCM already installed'
Assert-True (-not (Test-Path -LiteralPath (Join-Path $TrustRoot 'policy\service.json'))) 'Activation policy already exists'
$BrokerSid = $Broker.SID.Value
foreach ($Path in @('D:\AURA','D:\AURA\Trust',$TrustRoot,(Join-Path $TrustRoot 'bin'),$Source,(Join-Path $Source 'bin'))) {
    Assert-NoLink $Path
}
foreach ($Path in @($TrustRoot,(Join-Path $TrustRoot 'bin'))) {
    $Acl = Get-Acl -LiteralPath $Path
    Assert-True $Acl.AreAccessRulesProtected "Trust directory inherits ACL: $Path"
}

$InventoryPath = Join-Path $Source 'runtime-inventory.json'
Assert-Sha $InventoryPath $ExpectedInventorySha
Assert-Sha (Join-Path $Source 'provenance.json') $ExpectedProvenanceSha
Assert-Sha (Join-Path $Source 'operator-scripts\operator-scripts-inventory.json') $ExpectedScriptsSha
$Rows = @(Read-Inventory $InventoryPath)
Assert-True ($Rows.Count -eq 9028) "Expected exactly 9028 runtime inventory entries: $($Rows.Count)"
$Index = [collections.generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$Items = [collections.generic.List[object]]::new()
foreach ($Row in $Rows) {
    $Relative = [string]$Row.path
    if ($Relative.StartsWith('bin/', [StringComparison]::OrdinalIgnoreCase)) {
        $Relative = $Relative.Substring(4)
    }
    Assert-Relative $Relative
    $Hash = [string]$Row.sha256
    Assert-True ($Hash -cmatch '^[0-9a-f]{64}$') "Invalid runtime SHA: $Relative"
    Assert-True ($Index.Add($Relative.Replace('\','/'))) "Duplicate runtime path: $Relative"
    $File = Join-Path (Join-Path $Source 'bin') $Relative.Replace('/', '\')
    Assert-Sha $File $Hash
    $Items.Add([PSCustomObject]@{ Path = $Relative; Sha = $Hash })
}
$Actual = @(Get-ChildItem -LiteralPath (Join-Path $Source 'bin') -Recurse -File -Force)
Assert-True ($Actual.Count -eq $Rows.Count) 'Uninventoried extra/missing runtime file'
foreach ($File in @(Get-ChildItem -LiteralPath (Join-Path $Source 'bin') -Recurse -Force)) {
    Assert-NoLink $File.FullName
}
Write-Host 'PASS: Source runtime 9028 SHA-256 and no reparse points' -ForegroundColor Green

# Explicit cleanup only for a known failed, incomplete F2.6 stage.
# A partial stage is deleted ONLY if every file is in the trusted source
# inventory, has the same SHA-256 and has sealed SYSTEM/Admin/Broker RX ACLs.
# No broad bin cleanup; no wildcard deletion; never touches production bin.
if ($CleanupStale) {
    Assert-True ($StaleStageName -cmatch '^\.f26-staging-[0-9a-f]{32}$') 'Stale stage name must be a single 32-hex F2.6 staging folder'
    $Bin = Join-Path $TrustRoot 'bin'
    $Stage = Join-Path $Bin $StaleStageName
    $Final = Join-Path $Bin 'f26-38c42d1'
    Assert-True (-not (Test-Path -LiteralPath $Final)) 'Final target exists; do not remove prior stage'
    $StageItem = Get-Item -LiteralPath $Stage -Force -ErrorAction Stop
    Assert-True $StageItem.PSIsContainer 'Expected a single stale directory'
    Assert-SealedAcl $Stage $BrokerSid

    $Known = [collections.generic.Dictionary[string,string]]::new(
        [StringComparer]::OrdinalIgnoreCase
    )
    foreach ($Entry in $Items) {
        $Known.Add($Entry.Path.Replace('\','/'), $Entry.Sha)
    }
    $StaleFiles = @(Get-ChildItem -LiteralPath $Stage -Recurse -File -Force -ErrorAction Stop)
    Assert-True ($StaleFiles.Count -ge 1 -and $StaleFiles.Count -le 9028) 'Unexpected stale stage file count'
    $RootPrefix = $Stage.TrimEnd('\') + '\'
    foreach ($File in $StaleFiles) {
        Assert-True ($File.FullName.StartsWith($RootPrefix, [StringComparison]::OrdinalIgnoreCase)) 'Stale file escaped stage root'
        $Relative = $File.FullName.Substring($RootPrefix.Length).Replace('\','/')
        Assert-True ($Known.ContainsKey($Relative)) "Unrecognized stale file: $Relative"
        Assert-Sha $File.FullName $Known[$Relative]
        Assert-SealedAcl $File.FullName $BrokerSid
    }
    foreach ($Dir in @(Get-ChildItem -LiteralPath $Stage -Recurse -Directory -Force -ErrorAction Stop)) {
        Assert-SealedAcl $Dir.FullName $BrokerSid
        $Relative = $Dir.FullName.Substring($RootPrefix.Length).Replace('\','/')
        Assert-True (@($Known.Keys | Where-Object { $_.StartsWith($Relative + '/', [StringComparison]::OrdinalIgnoreCase) }).Count -gt 0) "Unrecognized stale directory: $Relative"
    }
    Remove-Item -LiteralPath $Stage -Recurse -Force -ErrorAction Stop
    Assert-True (-not (Test-Path -LiteralPath $Stage)) 'Stale stage not fully removed'
    Write-Host "PASS: Independently verified stale stage removed: $Stage" -ForegroundColor Green
    Write-Host 'NO CHANGE: Production bin target, SCM, service policy and Broker state'
    exit 0
}
if (-not $Promote) {
    Write-Host 'VERIFIED_ONLY: add -Promote to seal an inactive F2.6 candidate; never activates SCM'
    exit 0
}

$Bin = Join-Path $TrustRoot 'bin'
$Final = Join-Path $Bin 'f26-38c42d1'
Assert-True (-not (Test-Path -LiteralPath $Final)) 'Target already exists: manual review required'
$Nonce = [guid]::NewGuid().ToString('N')
$Stage = Join-Path $Bin ('.f26-staging-' + $Nonce)
$DirAcl = New-ProtectedAcl $true $BrokerSid
$FileAcl = New-ProtectedAcl $false $BrokerSid
[IO.Directory]::CreateDirectory($Stage, $DirAcl) | Out-Null
try {
    foreach ($Entry in $Items) {
        $Path = Join-Path $Stage $Entry.Path.Replace('/', '\')
        $Parent = Split-Path -Parent $Path
        $Parts = $Entry.Path.Replace('\', '/').Split('/')
        $Cursor = $Stage
        if ($Parts.Count -gt 1) {
            foreach ($Part in $Parts[0..($Parts.Count-2)]) {
                $Cursor = Join-Path $Cursor $Part
                if (-not (Test-Path -LiteralPath $Cursor)) {
                    [IO.Directory]::CreateDirectory($Cursor, $DirAcl) | Out-Null
                }
            }
        }
        $From = Join-Path (Join-Path $Source 'bin') $Entry.Path.Replace('/', '\')
        [IO.File]::Copy($From, $Path, $false)
        [IO.File]::SetAccessControl($Path, $FileAcl)
        Assert-Sha $Path $Entry.Sha
        Assert-SealedAcl $Path $BrokerSid
    }
    foreach ($Directory in @(Get-Item -LiteralPath $Stage) +
            @(Get-ChildItem -LiteralPath $Stage -Recurse -Directory -Force)) {
        Assert-SealedAcl $Directory.FullName $BrokerSid
    }
    $Copied = @(Get-ChildItem -LiteralPath $Stage -Recurse -File -Force)
    Assert-True ($Copied.Count -eq 9028) 'Promoted runtime count mismatch'
    $Python = Join-Path $Stage 'python.exe'
    Assert-True (Test-Path -LiteralPath $Python -PathType Leaf) 'Isolated python.exe missing'
    & $Python -I -c "import sys, cryptography, cffi, pycparser; import aura_core.osworld.audit_broker_service as b; assert sys.prefix == sys.base_prefix; print('PASS: isolated Python import')"
    Assert-True ($LASTEXITCODE -eq 0) 'Relocated Python 3.13 -I import failed'

    # Atomic same-volume directory rename; refuse any target collision.
    Assert-True (-not (Test-Path -LiteralPath $Final)) 'Final target appeared during verification'
    [IO.Directory]::Move($Stage, $Final)
    foreach ($Entry in $Items) {
        Assert-Sha (Join-Path $Final $Entry.Path.Replace('/', '\')) $Entry.Sha
    }
    Write-Host "PASS: inactive sealed F2.6 candidate promoted: $Final" -ForegroundColor Green
    Write-Host 'NO CHANGE: service.json absent, SCM absent, broker disabled, no live Ubuntu audit'
}
catch {
    Write-Warning "Promotion STOP: $($_.Exception.Message)"
    Write-Warning "Review protected candidate path manually: $Stage"
    throw
}
