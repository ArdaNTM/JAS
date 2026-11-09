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
$ProvenanceSha = 'dcba98548770f7610ce00313aa246179d7c2e00e2159182b71b584e35bfa0a0a'
$ScriptsInventorySha = '31c6efd24ad3bf2c193a2a6c8b6d36a59fe4231df5f2fcba2e7be0a2d12869f0'
$TrustRoot = 'D:\AURA\Trust\DockerBroker'
$StageRoot = Join-Path $TrustRoot 'staging-f26-38c42d1'
$AdminSid = 'S-1-5-32-544'
$SystemSid = 'S-1-5-18'

function Assert-Condition([bool]$Condition, [string]$Reason) {
    if (-not $Condition) { throw "STOP: $Reason" }
}

function Assert-Sha256Pin([string]$Value, [string]$Name) {
    Assert-Condition ($Value -cmatch '^[0-9a-f]{64}$') "Invalid SHA-256 pin ($Name): requires exactly 64 lower-case hex characters"
}

function Assert-AllSha256Pins {
    $Pinned = [ordered]@{
        SourceDigest = $SourceDigest
        RuntimeInventorySha = $RuntimeInventorySha
        ProvenanceSha = $ProvenanceSha
        ScriptsInventorySha = $ScriptsInventorySha
    }
    foreach ($Name in $Pinned.Keys) {
        Assert-Sha256Pin ([string]$Pinned[$Name]) $Name
    }
}

# Preflight applies to operator, real-token probes AND CI -SelfTest.
Assert-AllSha256Pins

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
    if ($Document -is [array]) { return $Document }
    foreach ($Property in @('files', 'entries', 'items', 'inventory')) {
        if ($null -ne $Document.PSObject.Properties[$Property]) {
            $Value = $Document.$Property
            Assert-Condition ($Value -is [array]) "Inventory $Property is not an array"
            return $Value
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

function Test-AncestorRuleUnsafe(
    [string]$Path,
    [Security.AccessControl.FileSystemAccessRule]$Ace,
    [string]$BrokerSid
) {
    if ($Ace.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow) {
        return $false
    }
    if (($Ace.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) -ne 0) {
        # An INHERIT_ONLY entry is not effective on this directory.
        return $false
    }
    $Sid = $Ace.IdentityReference.Value
    if ($Sid -in @($AdminSid, $SystemSid)) { return $false }
    # The Broker's identity is NOT a trusted mutator of ancestors.
    $Danger = [int][Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor
              [int][Security.AccessControl.FileSystemRights]::ChangePermissions -bor
              [int][Security.AccessControl.FileSystemRights]::TakeOwnership
    if ($Path -cne 'D:\') {
        # A non-root ancestor can itself be renamed with DELETE on that object.
        $Danger = $Danger -bor [int][Security.AccessControl.FileSystemRights]::Delete
    }
    if ($Path -cEq 'D:\AURA\Trust') {
        # The immediate protected trust parent must not admit untrusted writes.
        $Danger = $Danger -bor [int][Security.AccessControl.FileSystemRights]::Write
    }
    return (([int]$Ace.FileSystemRights -band $Danger) -ne 0)
}

function Assert-TrustedAncestors([string]$BrokerSid) {
    # Only effective ancestor rights capable of replacing/renaming the
    # protected branch are relevant. Broad D:\ Modify alone cannot delete
    # a protected D:\AURA child unless DELETE_CHILD is granted on D:\.
    # Non-root DELETE (rename) and WRITE_DAC/WRITE_OWNER are still blocked.
    foreach ($Parent in @('D:\', 'D:\AURA', 'D:\AURA\Trust')) {
        $Item = Get-Item -LiteralPath $Parent -Force -ErrorAction Stop
        Assert-Condition (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) "Reparse-point ancestor: $Parent"
        $Acl = Get-Acl -LiteralPath $Parent
        $Owner = $Acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
        Assert-Condition ($Owner -in @($AdminSid, $SystemSid)) "Untrusted ancestor owner: $Parent"
        $Rules = $Acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])
        foreach ($Ace in $Rules) {
            if (Test-AncestorRuleUnsafe $Parent $Ace $BrokerSid) {
                throw "STOP: Untrusted ancestor has effective DELETE/DELETE_CHILD/DACL/owner/write rights: $Parent ($($Ace.IdentityReference.Value)); mask=$([int]$Ace.FileSystemRights); propagation=$($Ace.PropagationFlags)"
            }
        }
    }
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
    foreach ($Ace in $Acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
        $Sid = $Ace.IdentityReference.Value
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
    $Resolved = @(& $Git -C $Repo rev-parse ($SourceCommit + "^{commit}") 2>$null)
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

function Get-ContentSHA256([byte[]]$Bytes) {
    $Hasher = [Security.Cryptography.SHA256]::Create()
    try {
        return [BitConverter]::ToString($Hasher.ComputeHash($Bytes)).Replace('-', '').ToLowerInvariant()
    }
    finally { $Hasher.Dispose() }
}

function Assert-PinnedFileHash([string]$Path, [string]$Expected) {
    $Item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    Assert-Condition (-not $Item.PSIsContainer -and
        ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) "Pinned evidence path is not a regular file: $Path"
    $Actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Actual -ceq $Expected) { return }
    Write-Warning "F2.6 PINNED EVIDENCE MISMATCH: $Path"
    Write-Warning "Expected SHA256: $Expected"
    Write-Warning "Observed SHA256: $Actual"
    Write-Warning "Observed byte count: $($Item.Length)"
    Write-Warning "Observed LastWriteTimeUtc: $($Item.LastWriteTimeUtc.ToString('o'))"

    if ($Item.Name -ceq 'provenance.json' -and $Item.Length -le 1048576) {
        # Diagnostic only: never silently repin or rewrite evidence.
        try {
            $Raw = [IO.File]::ReadAllBytes($Item.FullName)
            $Utf8 = [Text.UTF8Encoding]::new($false, $true)
            $Text = $Utf8.GetString($Raw)
            $CRLF = [string][char]13 + [char]10
            $LF = [string][char]10
            $Candidates = [ordered]@{
                utf8_without_bom = $Text.TrimStart([char]0xFEFF)
                lf_newlines = $Text.TrimStart([char]0xFEFF).Replace($CRLF, $LF)
                crlf_newlines = $Text.TrimStart([char]0xFEFF).Replace($CRLF, $LF).Replace($LF, $CRLF)
            }
            $Matches = @()
            foreach ($Name in $Candidates.Keys) {
                $Candidate = [Text.Encoding]::UTF8.GetBytes([string]$Candidates[$Name])
                if ((Get-ContentSHA256 $Candidate) -ceq $Expected) {
                    $Matches += $Name
                }
            }
            if ($Matches.Count -gt 0) {
                Write-Warning "ENCODING_ONLY_CANDIDATE: $($Matches -join ', '); independent byte review still required"
            }
            else {
                Write-Warning 'NO_SIMPLE_ENCODING_MATCH: do not repin unreviewed provenance bytes'
            }
            $Doc = ConvertFrom-Json -InputObject $Text
            if ($null -ne $Doc -and $Doc -is [pscustomobject]) {
                $Names = @($Doc.PSObject.Properties | ForEach-Object Name)
                Write-Warning "Provenance top-level JSON keys (not values): $($Names -join ', ')"
            }
        }
        catch {
            Write-Warning "Provenance UTF-8/JSON diagnostic could not be completed: $($_.Exception.GetType().Name)"
        }
    }
    throw "STOP: Pinned evidence hash mismatch: $Path; no silent hash replacement permitted"
}

function Assert-DeniedFileOpen([string]$Path, [IO.FileAccess]$Access) {
    # Do not use Test-Path: an inaccessible protected file can look missing.
    # File.Open is the decisive OS access check. Missing/IO errors fail closed.
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
    $RejectTruncation = $false
    try { Assert-Sha256Pin ('a' * 62) 'truncated-regression' }
    catch { $RejectTruncation = $_.Exception.Message.Contains('Invalid SHA-256 pin') }
    Assert-Condition $RejectTruncation '62-character SHA-256 pin must fail closed'
    Assert-Sha256Pin ('a' * 64) 'complete-regression'
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
    $Scratch = [IO.Path]::GetTempFileName()
    try {
        '[{"path":"one.py","sha256":"' + ('a' * 64) + '"},{"path":"two.py","sha256":"' + ('b' * 64) + '"}]' |
            Set-Content -LiteralPath $Scratch -Encoding Ascii
        Assert-Condition (@(Read-Entries $Scratch).Count -eq 2) 'Array JSON enumeration broken'
        '{"files":[{"path":"one.py","sha256":"' + ('a' * 64) + '"}]}' |
            Set-Content -LiteralPath $Scratch -Encoding Ascii
        Assert-Condition (@(Read-Entries $Scratch).Count -eq 1) 'Object JSON enumeration broken'
    }
    finally { Remove-Item -LiteralPath $Scratch -Force -ErrorAction SilentlyContinue }
    $Everyone = [Security.Principal.SecurityIdentifier]::new('S-1-5-11')
    $Admin = [Security.Principal.SecurityIdentifier]::new($AdminSid)
    $NoInherit = [Security.AccessControl.InheritanceFlags]::None
    $NoPropagate = [Security.AccessControl.PropagationFlags]::None
    $Allow = [Security.AccessControl.AccessControlType]::Allow
    $Modify = [Security.AccessControl.FileSystemAccessRule]::new(
        $Everyone, [Security.AccessControl.FileSystemRights]::Modify,
        $NoInherit, $NoPropagate, $Allow
    )
    Assert-Condition (-not (Test-AncestorRuleUnsafe 'D:\' $Modify 'S-1-5-21-1-2-3-4')) 'Root Modify alone must not fail protected-child boundary'
    Assert-Condition (Test-AncestorRuleUnsafe 'D:\AURA' $Modify 'S-1-5-21-1-2-3-4') 'Nonroot Modify/DELETE must fail closed'
    $DeleteChild = [Security.AccessControl.FileSystemAccessRule]::new(
        $Everyone, [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles,
        $NoInherit, $NoPropagate, $Allow
    )
    Assert-Condition (Test-AncestorRuleUnsafe 'D:\' $DeleteChild 'S-1-5-21-1-2-3-4') 'Root DELETE_CHILD must fail closed'
    $InheritOnly = [Security.AccessControl.FileSystemAccessRule]::new(
        $Everyone, [Security.AccessControl.FileSystemRights]::FullControl,
        [Security.AccessControl.InheritanceFlags]::ContainerInherit,
        [Security.AccessControl.PropagationFlags]::InheritOnly, $Allow
    )
    Assert-Condition (-not (Test-AncestorRuleUnsafe 'D:\AURA' $InheritOnly 'S-1-5-21-1-2-3-4')) 'Inherit-only ACE must not be treated as effective on parent'
    $AdminFull = [Security.AccessControl.FileSystemAccessRule]::new(
        $Admin, [Security.AccessControl.FileSystemRights]::FullControl,
        $NoInherit, $NoPropagate, $Allow
    )
    Assert-Condition (-not (Test-AncestorRuleUnsafe 'D:\AURA' $AdminFull 'S-1-5-21-1-2-3-4')) 'Trusted Administrators ACE must be allowed'
    $MissingPath = Join-Path $env:TEMP ('aura-f26-nonexistent-' + [guid]::NewGuid().ToString('N') + '.bin')
    $MissingDenied = $false
    try { Assert-DeniedFileOpen $MissingPath ([IO.FileAccess]::Read) }
    catch [IO.FileNotFoundException] { $MissingDenied = $true }
    Assert-Condition $MissingDenied 'Missing file must not count as permission denial'
    $Probe = [IO.Path]::GetTempFileName()
    try {
        [IO.File]::WriteAllBytes($Probe, [Text.Encoding]::UTF8.GetBytes('aura-provenance-mismatch-test'))
        $Denied = $false
        try { Assert-PinnedFileHash $Probe ('0' * 64) }
        catch { $Denied = $_.Exception.Message.Contains('Pinned evidence hash mismatch') }
        Assert-Condition $Denied 'Unpinned evidence file must fail closed'
    }
    finally { Remove-Item -LiteralPath $Probe -Force -ErrorAction SilentlyContinue }
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
Assert-TrustedAncestors $BrokerSid
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
