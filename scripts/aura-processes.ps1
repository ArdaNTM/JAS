# Repository-scoped process identification. Never kill unrelated processes.
function Test-AuraOwnedProcess {
    param([Parameter(Mandatory=$true)]$Process, [Parameter(Mandatory=$true)][string]$Root)
    $comparison = [StringComparison]::OrdinalIgnoreCase
    $command = ([string]$Process.CommandLine).Replace('/', '\')
    $exe = ([string]$Process.ExecutablePath).Replace('/', '\')
    if (-not $command -or -not $exe) { return $false }

    $corePython = Join-Path $Root "core\.venv\Scripts\python.exe"
    $alternatePython = Join-Path $Root ".venv\Scripts\python.exe"
    $research = Join-Path $Root "core\scripts\local_research_mcp.py"
    $vite = Join-Path $Root "aura-ui\node_modules\vite\bin\vite.js"
    $viteCli = Join-Path $Root "aura-ui\node_modules\vite\dist\node\cli.js"
    $uiDir = Join-Path $Root "aura-ui"
    $coreOwned = (
        ($exe.Equals($corePython, $comparison) -or $exe.Equals($alternatePython, $comparison)) -and
        $command -match '(?i)(?:^|\s)-m\s+aura_core(?:\s|$)'
    )
    $ownerReviewOwned = (
        ($exe.Equals($corePython, $comparison) -or $exe.Equals($alternatePython, $comparison)) -and
        $command -match '(?i)(?:^|\s)-m\s+aura_core\.evolution\.owner_control_plane_http(?:\s|$)'
    )
    $researchOwned = (
        $command.IndexOf($research, $comparison) -ge 0 -and
        ($exe.Equals($corePython, $comparison) -or $exe.Equals($alternatePython, $comparison))
    )
    $nodeExe = $exe -match '(?i)(?:^|\\)node\.exe$'
    $viteOwned = $nodeExe -and (
        $command.IndexOf($vite, $comparison) -ge 0 -or
        $command.IndexOf($viteCli, $comparison) -ge 0
    )
    # Some npm preview launchers use npm.cmd via cmd.exe. Only the
    # unambiguous repo-working-directory/preview command is recognized.
    $npmPreview = (
        $command.IndexOf($uiDir, $comparison) -ge 0 -and
        $command -match '(?i)\bnpm(?:\.cmd)?\b.*\brun\s+preview\b' -and
        $exe -match '(?i)(?:^|\\)cmd\.exe$'
    )
    return ($coreOwned -or $ownerReviewOwned -or $researchOwned -or $viteOwned -or $npmPreview)
}

function Stop-AuraStaleProcesses {
    param([Parameter(Mandatory=$true)][string]$Root)
    $all = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    $owned = @{}
    foreach ($process in $all) {
        if (Test-AuraOwnedProcess -Process $process -Root $Root) {
            $owned[[int]$process.ProcessId] = $true
        }
    }
    # Explicitly inspect the expected ports; never terminate a foreign owner.
    foreach ($port in @(8000, 4173, 5173, 8766)) {
        $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
        foreach ($listener in $listeners) {
            $ownerProcessId = [int]$listener.OwningProcess
            if ($ownerProcessId -le 0 -or $owned.ContainsKey($ownerProcessId)) { continue }
            $process = $all | Where-Object { [int]$_.ProcessId -eq $ownerProcessId } | Select-Object -First 1
            if ($null -ne $process -and (Test-AuraOwnedProcess -Process $process -Root $Root)) {
                $owned[$ownerProcessId] = $true
            }
        }
    }
    foreach ($processId in $owned.Keys) {
        Write-Host "Stopping repo-owned AURA process PID $processId"
        Stop-Process -Id ([int]$processId) -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 500
}

function Assert-AuraPortAvailable {
    param([Parameter(Mandatory=$true)][int]$Port)
    $listener = $null
    try {
        $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
        $listener.Start()
    } catch {
        throw "Port $Port is occupied by a process not safely identified as AURA. No other process will be terminated."
    } finally {
        if ($null -ne $listener) { $listener.Stop() }
    }
}
