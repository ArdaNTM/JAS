$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "aura-processes.ps1")

$root = "D:\AURA\JAS"
$py = Join-Path $root "core\.venv\Scripts\python.exe"
$vite = Join-Path $root "aura-ui\node_modules\vite\bin\vite.js"
$viteCli = Join-Path $root "aura-ui\node_modules\vite\dist\node\cli.js"
$fake = @(
    @{ CommandLine = ('"' + $py + '" -m aura_core'); ExecutablePath=$py; ProcessId=101; Expected=$true },
    @{ CommandLine = ('"C:\Program Files\nodejs\node.exe" "' + $vite + '" preview --port 4173'); ExecutablePath="C:\Program Files\nodejs\node.exe"; ProcessId=102; Expected=$true },
    @{ CommandLine = ('"C:\Program Files\nodejs\node.exe" "' + $viteCli + '" --port 5173'); ExecutablePath="C:\Program Files\nodejs\node.exe"; ProcessId=106; Expected=$true },
    @{ CommandLine = ('"' + $py + '" -m aura_core.evolution.owner_control_plane_http'); ExecutablePath=$py; ProcessId=107; Expected=$true },
    @{ CommandLine = ('"' + $py + '" -m aura_core.evolution.owner_control_plane_http_extra'); ExecutablePath=$py; ProcessId=108; Expected=$false },
    @{ CommandLine = ('"C:\\Python313\\python.exe" -m aura_core.evolution.owner_control_plane_http'); ExecutablePath="C:\\Python313\\python.exe"; ProcessId=109; Expected=$false },
    @{ CommandLine = ('"' + $py + '" -c "print(1)"'); ExecutablePath=$py; ProcessId=103; Expected=$false },
    @{ CommandLine = '"C:\Program Files\nodejs\node.exe" C:\AnotherApp\vite\bin\vite.js'; ExecutablePath="C:\Program Files\nodejs\node.exe"; ProcessId=104; Expected=$false },
    @{ CommandLine = '"C:\Python313\python.exe" -m aura_core'; ExecutablePath="C:\Python313\python.exe"; ProcessId=105; Expected=$false }
)
foreach ($row in $fake) {
    $actual = Test-AuraOwnedProcess -Process ([pscustomobject]$row) -Root $root
    if ([bool]$actual -ne [bool]$row.Expected) {
        throw "Process ownership mismatch for synthetic PID $($row.ProcessId)"
    }
}

$listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,0)
$listener.Start()
$port=($listener.LocalEndpoint).Port
try {
    $rejected=$false
    try { Assert-AuraPortAvailable -Port $port }
    catch { $rejected=$true }
    if (-not $rejected) { throw "Occupied port should fail closed" }
} finally { $listener.Stop() }
Assert-AuraPortAvailable -Port $port
# Verify that Owner health failure does not flow into Core/HUD teardown.
$launcher = [IO.File]::ReadAllText((Join-Path $PSScriptRoot "launch-aura-desktop.ps1"))
$probe = $launcher.IndexOf('Wait-ForHttp -Url "http://127.0.0.1:8766/health" -TimeoutSeconds 15 -RequireOk')
if ($probe -lt 0) { throw "Owner probe must require IPv4 HTTP 200" }
$localCatch = $launcher.IndexOf('    catch {', $probe)
$hudStart = $launcher.IndexOf('    $uiProcess = Start-UiWithRetry -Npm $Npm', $probe)
if ($localCatch -lt 0 -or $hudStart -lt 0 -or $localCatch -gt $hudStart) {
    throw "Owner readiness failure must be contained before HUD startup"
}
$browserStart = $launcher.IndexOf('    Open-AuraBrowser', $hudStart)
$diagnostic = $launcher.IndexOf('Show-LauncherError -Message $ownerWarning', $browserStart)
if ($browserStart -lt 0 -or $diagnostic -lt 0) {
    throw "Owner stderr warning must be displayed after the HUD opens"
}
if (-not $launcher.Contains('Read-LogSafe -Path $OwnerLogErr')) {
    throw "Owner review diagnostics must include captured stderr"
}
Write-Host "PASS: AURA owned-process and port regression"
