# AURA F2.6 offline operator acceptance; pinned to the source/runtime build.
# NO service installation, policy writes, account changes, signed receipts or Docker.
# Run Operator only from an independently checked, protected copy of this file.
[CmdletBinding()]
param(
    [ValidateSet('Operator', 'Agent', 'Auditor')]
    [string]$Mode = 'Operator',
    [switch]$SelfTest,
    [string]$ExpectedSid,
    [string]$Repo = 'D:\AURA\JAS',
    [string]$CandidateRoot = 'D:\AURA\JAS\artifacts\aura-f26-runtime-38c42d1'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$SourceCommit = '38c42d1308056cc157b7233280a7d51a2d5b998f'
$SourceDigest = '3c75ed20803ed60d786e3b2da64f70c90cef4490be4831e3e27e829b220b0ccd'
$RuntimeInventorySha = 'cb897595b79b9d2599ed90a12a60383ea9abd9b50a8eebe05dd929f094dd88a7'
$ProvenanceSha = 'dcba98548770f7610ce00313aa246179d7c2e00e2159182b71b584e35bfa0a'
$ScriptsInventorySha = '31c6efd24ad3bf2c193a2a6c8b6d36a59fe4231df5f2fcba2e7be0a2d12869f0'
$TrustRoot = 'D:\AURA\Trust\DockerBroker'
$StageRoot = Join-Path $TrustRoot 'staging-f26-38c42d1'
$AdminSid = 'S-1-5-32-544'
$SystemSid = 'S-1-5-18'

function Assert-Condition([bool]$Condition, [string]$Reason) {
    if (-not $Condition) { throw "STOP: $Reason" }
}

function Assert-SafeRelative([string]$Relative) {
    Assert-Condition (-not [string]::IsNullOrWhiteSpace($Relative)) 'Empty inventory path'
    Assert-Condition ($Relative -notmatch '(^[\\/]|^[A-Za-z]:|:|[\x00-\x1f])') 'Absolute or invalid inventory path'
    $Parts = $Relative.Replace('\', '/').Split('/')
    Assert-Condition ($Parts.Count -gt 0) 'Empty inventory path components'
    foreach ($Part in $Parts) {
        Assert-Condition ($Part -notin @('', '.', '..')) 'Traversal/empty inventory path component'
        Assert-Condition ($Part -notmatch '[<>:"|?*]' -and -not $Part.EndsWith('.') -and -not $Part.EndsWith(' ')) 'Unsafe inventory filename'
    }
}

function Assert-NoReparse([string]$Directory) {
    $Root = Get-Item -LiteralPath $Directory -Force -ErrorAction Stop
    Assert-Condition $Root.PSIsContainer "Not a directory: $Directory"
    $Items = @( $Root ) + @( Get-ChildItem -LiteralPath $Directory -Force -Recurse )
    foreach ($Item in $Items) {
        Assert-Condition (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) "Reparse point: $($Item.FullName)"
    }
}

function Read-Entries([string]$ManifestFile) {
    $Document = ConvertFrom-Json -InputObject (Get-Content -LiteralPath $ManifestFile -Raw -Encoding UTF8)
    if ($null -eq $Document) { throw "STOP: Null JSON inventory" }
    if ($Document -is [array]) { return ,$Document }
    foreach ($Property in @('files', 'entries', 'items', 'inventory')) {
        if ($null -ne $Document.PSObject.Properties[$Property]) {
            $Value = $Document.$Property
            Assert-Condition ($Value -is [array]) "Inventory $Property is not an array"
            return ,$Value
        }
    }
    throw "STOP: Unsupported inventory JSON shape: $ManifestFile"
}

function Get-Field($Row, [string[]]$Names) {
    foreach ($Name in $Names) {
        $Property = $Row.PSObject.Properties[$Name]
        if ($null -ne $Property -and $Property.Value -is [string]) {
            return [string]$Property.Value
        }
    }
    throw "STOP: Missing required inventory field ($($Names -join ','))"
}

function Check-Inventory(
    [string]$Directory, [string]$InventoryPath, [int]$Count,
    [switch]$AllowBinPrefix
) {
    Assert-NoReparse $Directory
    $Rows = @(Read-Entries $InventoryPath)
    Assert-Condition ($Rows.Count -eq $Count) "Inventory count $($Rows.Count), expected $Count"
    $Index = [collections.generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($Row in $Rows) {
        $Relative = Get-Field $Row @('path', 'relative_path', 'relativePath')
        if ($AllowBinPrefix -and $Relative.StartsWith('bin/', [StringComparison]::OrdinalIgnoreCase)) {
            $Relative = $Relative.Substring(4)
        }
        Assert-SafeRelative $Relative
        Assert-Condition ($Index.Add($Relative.Replace('\', '/'))) "Duplicate inventory path $Relative"
        $Hash = (Get-Field $Row @('sha256', 'hash', 'digest')).ToLowerInvariant()
        if ($Hash.StartsWith('sha256:')) { $Hash = $Hash.Substring(7) }
        Assert-Condition ($Hash -cmatch '^[0-9a-f]{64}$') "Invalid SHA-256: $Relative"
        $Path = Join-Path $Directory $Relative.Replace('/', '\')
        $File = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        Assert-Condition (-not $File.PSIsContainer) "Inventory entry is a directory: $Relative"
        $Actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
        Assert-Condition ($Actual -ceq $Hash) "File hash mismatch: $Relative"
    }
    $ActualFiles = @(Get-ChildItem -LiteralPath $Directory -Recurse -File -Force)
    Assert-Condition ($ActualFiles.Count -eq $Count) "Unexpected files in $Directory ($($ActualFiles.Count) vs $Count)"
    $Prefix = [IO.Path]::GetFullPath($Directory).TrimEnd('\') + '\'
    foreach ($File in $ActualFiles) {
        Assert-Condition ($File.FullName.StartsWith($Prefix, [StringComparison]::OrdinalIgnoreCase)) 'Inventory file escaped root'
        $Relative = $File.FullName.Substring($Prefix.Length).Replace('\', '/')
        Assert-Condition ($Index.Contains($Relative)) "Uninventoried file: $Relative"
    }
    Write-Host "PASS: $Count inventoried files: $Directory"
}

function Assert-ProtectedAcl([string]$FilePath, [string]$BrokerSid) {
    $Item = Get-Item -LiteralPath $FilePath -Force -ErrorAction Stop
    Assert-Condition (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) "Reparse point: $FilePath"
    $Acl = Get-Acl -LiteralPath $FilePath
    Assert-Condition $Acl.AreAccessRulesProtected "Inherited ACL: $FilePath"
    $Owner = $Acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    Assert-Condition ($Owner -ceq $AdminSid) "Unexpected owner: $FilePath"
    $Allowed = @($AdminSid, $SystemSid, $BrokerSid)
    $ForbiddenBroker = [int][Security.AccessControl.FileSystemRights]::Write -bor
                       [int][Security.AccessControl.FileSystemRights]::Delete -bor
                       [int][Security.AccessControl.FileSystemRights]::ChangePermissions -bor
                       [int][Security.AccessControl.FileSystemRights]::TakeOwnership -bor
                       [int][Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles
    foreach ($Ace in $Acl.Access) {
        $Sid = $Ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
        Assert-Condition ($Sid -in $Allowed -and -not $Ace.IsInherited -and
            $Ace.AccessControlType -eq 'Allow') "Unexpected NTFS ACE: $FilePath"
        if ($Sid -ceq $BrokerSid) {
            Assert-Condition (([int]$Ace.FileSystemRights -band $ForbiddenBroker) -eq 0) "Broker has write rights: $FilePath"
        }
    }
}

function Assert-SafetyState {
    $Broker = Get-LocalUser -Name 'AuraDockerBroker' -ErrorAction Stop
    Assert-Condition (-not $Broker.Enabled) 'Broker account enabled'
    Assert-Condition ($null -eq (Get-CimInstance Win32_Service -Filter "Name='AuraOSWorldAuditBroker'")) 'SCM service exists'
    Assert-Condition (-not (Test-Path -LiteralPath (Join-Path $TrustRoot 'policy\service.json'))) 'service.json exists'
    return $Broker.SID.Value
}

function Check-SourceLock {
    $Git = 'C:\Program Files\Git\cmd\git.exe'
    Assert-Condition (Test-Path -LiteralPath $Git -PathType Leaf) 'Pinned Git executable missing'
    $Resolved = @(& $Git -C $Repo rev-parse "$SourceCommit^" 2>$null)
    Assert-Condition ($LASTEXITCODE -eq 0 -and @($Resolved).Count -eq 1 -and $Resolved[0].Trim() -ceq $SourceCommit) 'Pinned Git commit missing'
    $Manifest = Join-Path $StageRoot 'snapshot\release-manifest.final.json'
    $Document = ConvertFrom-Json -InputObject (Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8)
    Assert-Condition ($Document.schema -ceq 'aura.release-lock.v2') 'Unexpected release schema'
    Assert-Condition ($Document.release_digest -ceq "sha256:$SourceDigest") 'Wrong release digest'
    Assert-Condition ([int]$Document.file_count -eq 349) 'Wrong release inventory count'
    $Rows = @(Read-Entries $Manifest)
    Assert-Condition ($Rows.Count -eq 349) 'Incomplete release-lock entries'
    $Builder = [Text.StringBuilder]::new()
    foreach ($Row in $Rows) {
        $Rel = Get-Field $Row @('path')
        Assert-SafeRelative $Rel
        $Hash = (Get-Field $Row @('sha256')).ToLowerInvariant()
        $File = Join-Path $StageRoot ("snapshot\" + $Rel.Replace('/', '\'))
        Assert-Condition ((Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $Hash) "Release file mismatch: $Rel"
        [void]$Builder.Append($Rel + [char]9 + $Hash + [char]10)
    }
    $Sha = [Security.Cryptography.SHA256]::Create()
    try {
        $Digest = [BitConverter]::ToString($Sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Builder.ToString()))).Replace('-', '').ToLowerInvariant()
    }
    finally { $Sha.Dispose() }
    Assert-Condition ($Digest -ceq $SourceDigest) 'Combined release lock mismatch'
    Write-Host 'PASS: 38c42d1 source and 349-file release lock'
}

function Assert-PinnedFileHash([string]$Path, [string]$Expected) {
    $Actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    Assert-Condition ($Actual -ceq $Expected) "Pinned evidence hash mismatch: $Path"
}

function Assert-DeniedFileOpen([string]$Path, [IO.FileAccess]$Access) {
    Assert-Condition (Test-Path -LiteralPath $Path -PathType Leaf) "Test target missing: $Path"
    $Handle = $null
    try {
        $Handle = [IO.File]::Open($Path, [IO.FileMode]::Open, $Access, [IO.FileShare]::ReadWrite)
        throw "STOP: Access permitted ($Access) to $Path"
    }
    catch [UnauthorizedAccessException] {
        Write-Host "PASS: OS denied $Access access to $Path"
    }
    finally { if ($null -ne $Handle) { $Handle.Dispose() } }
}

if ($SelfTest) {
    Assert-SafeRelative 'bin/aura_core/osworld/audit_broker_service.py'
    foreach ($Bad in @('../escape', 'C:\Windows\evil', 'a//b', 'a/./b', 'a\b\..\c')) {
        $WasDenied = $false
        try { Assert-SafeRelative $Bad } catch { $WasDenied = $true }
        Assert-Condition $WasDenied "Unsafe relative path accepted: $Bad"
    }
    $Doc = [pscustomobject]@{ files = @([pscustomobject]@{ path = 'one.py'; sha256 = ('a' * 64) }) }
    $TestJson = $Doc | ConvertTo-Json -Depth 3
    $Parsed = ConvertFrom-Json -InputObject $TestJson
    Assert-Condition (@($Parsed.files).Count -eq 1) 'PowerShell 5.1 JSON array handling broke'
    Write-Host 'PASS: F2.6 operator verifier static self-tests'
    exit 0
}

Assert-Condition ($env:OS -ceq 'Windows_NT') 'Windows-only operator acceptance'
$BrokerSid = Assert-SafetyState
$TrustKey = Join-Path $TrustRoot 'keys\ubuntu-transport-ed25519'
$PayloadScript = Join-Path $StageRoot 'payload\aura_docker_broker_service.py'

if ($Mode -in @('Agent', 'Auditor')) {
    Assert-Condition ($ExpectedSid -cmatch '^S-1-5-21-(?:[0-9]+-){3}[0-9]+$') 'Expected user SID required for real-token probe'
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    Assert-Condition ($Identity.User.Value -ceq $ExpectedSid -and $ExpectedSid -cne $BrokerSid) 'Actual token SID mismatch'
    $Groups = @(& (Join-Path $env:SystemRoot 'System32\whoami.exe') /groups /fo csv)
    Assert-Condition ($LASTEXITCODE -eq 0) 'Cannot inspect process token groups'
    Assert-Condition (-not (($Groups -join ' ') -match 'S-1-5-32-544')) 'Administrators SID in token; separate acceptance required'
    foreach ($Path in @($TrustKey, $PayloadScript)) {
        Assert-DeniedFileOpen $Path ([IO.FileAccess]::Read)
        Assert-DeniedFileOpen $Path ([IO.FileAccess]::Write)
    }
    Write-Host "PASS: $Mode actual token $ExpectedSid could not open protected key or payload"
    Write-Host 'NOTE: Local operator must independently witness the real logon session.'
    exit 0
}

$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = [Security.Principal.WindowsPrincipal]::new($Identity)
Assert-Condition ($Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) 'Elevated independent operator token required'
foreach ($Path in @($TrustRoot, (Join-Path $TrustRoot 'bin'), $StageRoot,
    (Join-Path $StageRoot 'payload'))) {
    Assert-ProtectedAcl $Path $BrokerSid
}
Check-SourceLock
Check-Inventory (Join-Path $StageRoot 'payload') (Join-Path $StageRoot 'payload-review.json') 265

$Inventory = Join-Path $CandidateRoot 'runtime-inventory.json'
$Provenance = Join-Path $CandidateRoot 'provenance.json'
$ScriptInventory = Join-Path $CandidateRoot 'operator-scripts\operator-scripts-inventory.json'
Assert-PinnedFileHash $Inventory $RuntimeInventorySha
Assert-PinnedFileHash $Provenance $ProvenanceSha
Assert-PinnedFileHash $ScriptInventory $ScriptsInventorySha
Write-Host 'PASS: Three pinned Work runtime evidence documents'

$RuntimeBin = Join-Path $CandidateRoot 'bin'
Check-Inventory $RuntimeBin $Inventory 9028 -AllowBinPrefix
Write-Host 'PASS: F2.6 source and runtime candidate integrity inspection'
Write-Host 'PENDING: Real Agent/Auditor token negative-access tests (separate Windows logons)'
Write-Host 'PENDING: Independent immutable operator staging and NTFS review of all runtime files'
Write-Host 'NO CHANGE: Broker disabled; SCM absent; service.json absent; deny_only remains enforced'
Write-Host 'ACCEPTANCE_BLOCKED: Do not copy candidate into production bin or activate SCM'
exit 2
