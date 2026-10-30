$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "aura-app-window.ps1")

$argsForApp = @(Get-AuraAppLaunchArguments -Url "http://127.0.0.1:5173/")
if ($argsForApp.Count -ne 2 -or
    $argsForApp[0] -ne "--app=http://127.0.0.1:5173/" -or
    $argsForApp[1] -ne "--new-window") {
    throw "Local app-mode arguments were not generated correctly"
}
foreach ($unsafe in @(
    "https://example.com/", "http://localhost:5173/",
    "http://127.0.0.1:5173/path", "file:///C:/secret.txt",
    "http://127.0.0.1:5173/?other=1", "http://127.0.0.1:5173/#frag"
)) {
    $rejected = $false
    try { @(Get-AuraAppLaunchArguments -Url $unsafe) | Out-Null }
    catch { $rejected = $true }
    if (-not $rejected) { throw "Unsafe app-mode URL accepted" }
}
Write-Host "PASS: AURA app-mode launch arguments"
