#requires -Version 5.1
<#
F2.7 immutable sealed-runtime real Windows token negative access check.
Run ONLY from a separately Git-blob-verified, Administrator-owned,
non-writable read-only runner. Does not alter runtime, account privileges,
service policy, SCM, SSH, operator approval or the manifest.
The independent Administrator must FIRST check the exact 9,044-file
inventory hash, all 3 file hashes, and the inaccessible runtime ACL.
This script MUST NOT read operator-only inventory under Agent/Auditor.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [ValidateSet('Agent','Auditor')][string]$Mode='Agent',
    [string]$ExpectedSid,
    [switch]$SelfTest
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'

$Target='D:\AURA\Trust\DockerBroker\bin\f27-26ffdba485cc'
$ExpectedManifestSha='d9eb33c8ec0c494aec1039919699d4362e5222684048b160589b5bf88adcf21d'
$Targets=@('python.exe','python3.dll','DLLs\_asyncio.pyd')

function Assert-True([bool]$Condition,[string]$Reason){
    if(-not $Condition){throw "STOP: $Reason"}
}
function Assert-Denied([string]$Path,[IO.FileAccess]$Access){
    $Handle=$null
    try {
        $Handle=[IO.File]::Open(
            $Path,[IO.FileMode]::Open,$Access,[IO.FileShare]::ReadWrite)
        throw "STOP: Unexpected $Access access to F2.7 sealed runtime: $Path"
    }catch [UnauthorizedAccessException]{
        Write-Host "PASS: F2.7 protected runtime denied $Access handle" -ForegroundColor Green
    }finally{
        if($null -ne $Handle){$Handle.Dispose()}
    }
}
if($SelfTest){
    Assert-True ($Target -ceq 'D:\AURA\Trust\DockerBroker\bin\f27-26ffdba485cc') 'Unpinned runtime'
    Assert-True ($ExpectedManifestSha -ceq 'd9eb33c8ec0c494aec1039919699d4362e5222684048b160589b5bf88adcf21d') 'Unpinned manifest'
    Assert-True ($Targets.Count -eq 3) 'Wrong target count'
    Assert-True (@($Targets|Select-Object -Unique).Count -eq 3) 'Duplicate target'
    foreach($Relative in $Targets){
        Assert-True ($Relative -notmatch '(^[\\/]|^[A-Za-z]:|:|\.\.|[\x00-\x1f])') 'Unsafe target'
    }
    Assert-True ([IO.FileAccess]::Read -ne [IO.FileAccess]::Write) 'Identical probe access'
    Write-Host 'PASS: F2.7 9044-file sealed-runtime token test static selftest'
    exit 0
}
Assert-True ($env:OS -ceq 'Windows_NT') 'Windows only'
Assert-True ($ExpectedSid -cmatch '^S-1-5-21-(?:[0-9]+-){3}[0-9]+$') 'Independent operator-pinned local SID required'
$Identity=[Security.Principal.WindowsIdentity]::GetCurrent()
Assert-True ($null -ne $Identity.User -and $Identity.User.Value -ceq $ExpectedSid) 'Real Windows token does not match pinned SID'
$Principal=[Security.Principal.WindowsPrincipal]::new($Identity)
Assert-True (-not $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) 'Administrator token forbidden'
$AdminGroups=@($Identity.Groups|Where-Object{$_.Value -ceq 'S-1-5-32-544'})
Assert-True ($AdminGroups.Count -eq 0) 'Administrator group present in real token'
foreach($Relative in $Targets){
    $Path=Join-Path $Target $Relative
    Assert-Denied $Path ([IO.FileAccess]::Read)
    Assert-Denied $Path ([IO.FileAccess]::Write)
}
Write-Host "PASS: $Mode real token SID verified; six F2.7 sealed-runtime handles denied"
Write-Host 'NOTE: The parent operator independently validates the target SHA-256 manifest.'
