$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "aura-processes.ps1")

$root = "D:\AURA\JAS"
$py = Join-Path $root "core\.venv\Scripts\python.exe"
$vite = Join-Path $root "aura-ui\node_modules\vite\bin\vite.js"
$fake = @(
    @{ CommandLine = ('"' + $py + '" -m aura_core'); ExecutablePath=$py; ProcessId=101; Expected=$true },
    @{ CommandLine = ('"C:\Program Files\nodejs\node.exe" "' + $vite + '" --port 5173'); ExecutablePath="C:\Program Files\nodejs\node.exe"; ProcessId=102; Expected=$true },
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
Write-Host "PASS: AURA owned-process and port regression"
