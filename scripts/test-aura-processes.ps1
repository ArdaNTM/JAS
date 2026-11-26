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


# Exercise the exact production probe with a real IPv4 TCP listener.
# Extract only the function, never execute the desktop launcher.
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput($launcher, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -gt 0) { throw "Launcher parsing failed" }
$probeFunction = $ast.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq "Wait-ForHttp"
}, $true)
if ($null -eq $probeFunction) { throw "Health probe function missing" }
. ([scriptblock]::Create($probeFunction.Extent.Text))
$portFile = Join-Path ([IO.Path]::GetTempPath()) ("aura-probe-" + [Guid]::NewGuid().ToString("N") + ".txt")
$oldProxy = [Net.WebRequest]::DefaultWebProxy
$job = $null
try {
    # A hostile/unreachable system proxy must not affect the local probe.
    [Net.WebRequest]::DefaultWebProxy = [Net.WebProxy]::new("http://127.0.0.1:1", $false)
    $job = Start-Job -ArgumentList $portFile -ScriptBlock {
        param($readyFile)
        $ErrorActionPreference = "Stop"
        $server = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
        $server.Start()
        try {
            [IO.File]::WriteAllText($readyFile, [string]$server.LocalEndpoint.Port)
            foreach ($status in @("503 Service Unavailable", "200 OK", "302 Found")) {
                $client = $server.AcceptTcpClient()
                try {
                    $stream = $client.GetStream()
                    $stream.ReadTimeout = 5000
                    $reader = [IO.StreamReader]::new($stream)
                    do { $line = $reader.ReadLine() } while ($null -ne $line -and $line -ne "")
                    $header = "HTTP/1.1 $status" + [char]13 + [char]10 +
                        "Content-Length: 0" + [char]13 + [char]10 +
                        "Location: /not-health" + [char]13 + [char]10 +
                        "Connection: close" + [char]13 + [char]10 + [char]13 + [char]10
                    $bytes = [Text.Encoding]::ASCII.GetBytes($header)
                    $stream.Write($bytes, 0, $bytes.Length)
                    $stream.Flush()
                } finally { $client.Close() }
            }
        } finally { $server.Stop() }
    }
    $deadline = (Get-Date).AddSeconds(30)
    while (-not (Test-Path -LiteralPath $portFile) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 100
    }
    if (-not (Test-Path -LiteralPath $portFile)) { throw "Probe test listener did not start" }
    $probePort = [int]([IO.File]::ReadAllText($portFile))
    $url = "http://127.0.0.1:$probePort/health"
    if (-not (Wait-ForHttp -Url $url -TimeoutSeconds 10 -RequireOk)) {
        throw "Direct health probe failed: $script:LastHttpProbe"
    }
    if ($script:LastHttpProbe -notlike "HTTP 200*") { throw "503 was incorrectly accepted" }
    if (Wait-ForHttp -Url $url -TimeoutSeconds 2 -RequireOk) { throw "Redirect was incorrectly accepted" }
    $finished = [Diagnostics.Process]::Start("cmd.exe", "/d /c exit 17")
    try {
        $finished.WaitForExit()
        if (Wait-ForHttp -Url $url -TimeoutSeconds 10 -RequireOk -ExpectedProcess $finished) {
            throw "Exited launcher was incorrectly accepted"
        }
        if ($script:LastHttpProbe -ne "Process exited (code 17)") {
            throw "Missing exit-code diagnostic: $script:LastHttpProbe"
        }
    } finally { $finished.Dispose() }
} finally {
    [Net.WebRequest]::DefaultWebProxy = $oldProxy
    if ($null -ne $job) {
        Stop-Job $job -ErrorAction SilentlyContinue
        Remove-Job $job -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $portFile -Force -ErrorAction SilentlyContinue
}
Write-Host "PASS: real loopback health, proxy bypass, 503 retry, redirect rejection, exit diagnostics"
