# Windows-only, repository-scoped AURA process ownership checks.
# Never terminate arbitrary Node, Python, Uvicorn, or other project processes.
function Test-AuraOwnedProcess {
    param([Parameter(Mandatory=$true)]$Process, [Parameter(Mandatory=$true)][string]$Root)
    $command = ([string]$Process.CommandLine).Replace("/", "\\")
    $executable = [string]$Process.ExecutablePath
    if (-not $command) { return $false }
    $corePython = Join-Path $Root "core\.venv\Scripts\python.exe"
    $alternatePython = Join-Path $Root ".venv\Scripts\python.exe"
    $researchScript = Join-Path $Root "core\scripts\local_research_mcp.py"
    $viteScript = Join-Path $Root "aura-ui\node_modules\vite\bin\vite.js"
    $comparison = [StringComparison]::OrdinalIgnoreCase
    $isCore = ($command.IndexOf($corePython,$comparison) -ge 0 -or
               $command.IndexOf($alternatePython,$comparison) -ge 0 -or
               $executable.Equals($corePython,$comparison) -or
               $executable.Equals($alternatePython,$comparison)) -and
              $command -match '(?i)(?:^|\s)-m\s+aura_core(?:\s|$)'
    $isResearch = $command.IndexOf($researchScript,$comparison) -ge 0
    $isVite = $command.IndexOf($viteScript,$comparison) -ge 0 -and
              $executable -match '(?i)node(?:\.exe)?$'
    return ($isCore -or $isResearch -or $isVite)
}

function Stop-AuraStaleProcesses {
    param([Parameter(Mandatory=$true)][string]$Root)
    $all = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    foreach ($process in $all) {
        if (-not (Test-AuraOwnedProcess -Process $process -Root $Root)) { continue }
        Write-Host "Stopping stale AURA process PID $($process.ProcessId)"
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Assert-AuraPortAvailable {
    param([Parameter(Mandatory=$true)][int]$Port)
    $listener = $null
    try {
        $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
        $listener.Start()
    } catch {
        throw "Port $Port is occupied. AURA will not switch ports or stop non-AURA processes. Check Get-NetTCPConnection -LocalPort $Port."
    } finally {
        if ($null -ne $listener) { $listener.Stop() }
    }
}
