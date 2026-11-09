#requires -Version 5.1
# F2.7 post-promotion NON-MUTATING real-token access probe.
[CmdletBinding()]
param(
    [ValidateSet('Agent','Auditor')][string]$Mode = 'Agent',
    [string]$ExpectedSid,
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
if ($SelfTest) {
    Assert-Check ($Target -ceq 'D:\AURA\Trust\DockerBroker\bin\f26-38c42d1') 'Unpinned candidate'
    Assert-Check ([IO.FileAccess]::Read -ne [IO.FileAccess]::Write) 'Identical handles'
    Write-Host 'PASS: F2.7 post-promotion token-probe static selftest'
    exit 0
}
Assert-Check ($env:OS -ceq 'Windows_NT') 'Windows-only test'
Assert-Check ($ExpectedSid -cmatch '^S-1-5-21-(?:[0-9]+-){3}[0-9]+$') 'Operator-verified SID required'
$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
Assert-Check ($null -ne $Identity.User -and $Identity.User.Value -ceq $ExpectedSid) 'Real token SID mismatch'
$Principal = [Security.Principal.WindowsPrincipal]::new($Identity)
Assert-Check (-not $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) 'Elevated token forbidden'
$AdminGroups = @($Identity.Groups | Where-Object { $_.Value -ceq 'S-1-5-32-544' })
Assert-Check ($AdminGroups.Count -eq 0) 'Administrator SID appears in token'
foreach ($Name in @(
    'python.exe',
    'aura_docker_broker_service.py',
    'aura_core\osworld\audit_broker_service.py'
)) {
    $Path = Join-Path $Target $Name
    Assert-Denied $Path ([IO.FileAccess]::Read)
    Assert-Denied $Path ([IO.FileAccess]::Write)
}
Write-Host "PASS: $Mode actual token cannot read/write sealed F2.6 runtime"
Write-Host 'NOTE: Real user/logon identity must be witnessed independently.'
