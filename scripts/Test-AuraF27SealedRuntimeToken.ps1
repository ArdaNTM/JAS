#requires -Version 5.1
# F2.7 post-promotion NON-MUTATING real-token access probe.
# Tests two observed F2.6 root binaries plus an independently inventory-backed nested Python module.
# Missing files are errors and must never count as denied access.
[CmdletBinding()]
param(
    [ValidateSet('Agent','Auditor')][string]$Mode = 'Agent',
    [string]$ExpectedSid,
    [string]$NestedRelativePath,
    [switch]$SelfTest
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Target = 'D:\AURA\Trust\DockerBroker\bin\f26-38c42d1'
function Assert-Check([bool]$Condition,[string]$Message) {
    if (-not $Condition) { throw "STOP: $Message" }
}
function Assert-Denied([string]$Path,[IO.FileAccess]$Access) {
    $Handle = $null
    try {
        $Handle = [IO.File]::Open(
            $Path,[IO.FileMode]::Open,$Access,[IO.FileShare]::ReadWrite)
        throw "STOP: unexpected $Access access to protected runtime: $Path"
    }
    catch [UnauthorizedAccessException] {
        Write-Host "PASS: protected runtime denied $Access handle" -ForegroundColor Green
    }
    finally { if ($null -ne $Handle) { $Handle.Dispose() } }
}
function Assert-NestedProbePath([string]$Relative) {
    # Operator verifies this exact path from the 9,028-file pinned
    # inventory before executing the script in limited OS tokens.
    Assert-Check (-not [string]::IsNullOrWhiteSpace($Relative)) 'Nested probe path required'
    Assert-Check ($Relative.Length -le 512 -and
        $Relative -notmatch '(^[\\/]|^[A-Za-z]:|:|[<>|?*]|[\x00-\x1f])') 'Unsafe nested probe path'
    $Parts = $Relative.Replace('\','/').Split('/')
    Assert-Check ($Parts.Count -ge 2) 'Nested probe must be in a subdirectory'
    foreach ($Part in $Parts) {
        Assert-Check ($Part -notin @('','.','..') -and
            -not $Part.EndsWith('.') -and -not $Part.EndsWith(' ')) 'Invalid nested probe segment'
    }
    Assert-Check ($Parts[$Parts.Count-1] -match '\.(py|pyd)$') 'Nested probe must be an inventoried Python module'
}
if ($SelfTest) {
    Assert-Check ($Target -ceq 'D:\AURA\Trust\DockerBroker\bin\f26-38c42d1') 'Unpinned candidate'
    Assert-Check ([IO.FileAccess]::Read -ne [IO.FileAccess]::Write) 'Identical handles'
    Assert-NestedProbePath 'Lib/site-packages/example/module.py'
    foreach ($Bad in @('../escape.py','C:\evil.py','missing.py','dir/../escape.py','dir\bad:ads.py','\\server\share.py','dir/file.txt')) {
        $Rejected = $false
        try { Assert-NestedProbePath $Bad } catch { $Rejected = $true }
        Assert-Check $Rejected "Unsafe nested probe accepted: $Bad"
    }
    Write-Host 'PASS: F2.7 post-promotion token-probe static selftest'
    exit 0
}
Assert-Check ($env:OS -ceq 'Windows_NT') 'Windows-only test'
Assert-Check ($ExpectedSid -cmatch '^S-1-5-21-(?:[0-9]+-){3}[0-9]+$') 'Operator-verified SID required'
Assert-NestedProbePath $NestedRelativePath
$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
Assert-Check ($null -ne $Identity.User -and $Identity.User.Value -ceq $ExpectedSid) 'Real token SID mismatch'
$Principal = [Security.Principal.WindowsPrincipal]::new($Identity)
Assert-Check (-not $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) 'Elevated token forbidden'
$AdminGroups = @($Identity.Groups | Where-Object { $_.Value -ceq 'S-1-5-32-544' })
Assert-Check ($AdminGroups.Count -eq 0) 'Administrator SID appears in token'
foreach ($Name in @(
    'python.exe',
    'python3.dll',
    $NestedRelativePath
)) {
    $Path = Join-Path $Target $Name
    Assert-Denied $Path ([IO.FileAccess]::Read)
    Assert-Denied $Path ([IO.FileAccess]::Write)
}
Write-Host "PASS: $Mode actual token cannot read/write sealed F2.6 runtime"
Write-Host 'NOTE: Real user/logon identity must be witnessed independently.'
