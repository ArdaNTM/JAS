$ErrorActionPreference = "Stop"

$Root = "D:\AURA\JAS"
$Core = Join-Path $Root "core"
$Ui = Join-Path $Root "aura-ui"

$CoreLogOut = Join-Path $Root "aura-daemon.stdout.log"
$CoreLogErr = Join-Path $Root "aura-daemon.stderr.log"
$UiLogOut = Join-Path $Root "aura-ui.stdout.log"
$UiLogErr = Join-Path $Root "aura-ui.stderr.log"

function Stop-ProcessTreeSafe {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ProcessId
    )

    if ($ProcessId -le 0) {
        return
    }

    try {
        & taskkill.exe /F /T /PID $ProcessId 2>$null | Out-Null
    }
    catch {
    }

    try {
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    }
    catch {
    }
}

function Stop-AuraRelatedProcesses {
    $processNames = @(
        "python.exe",
        "pythonw.exe",
        "node.exe",
        "cmd.exe"
    )

    $auraMarkers = @(
        "aura_core",
        "local_research_mcp",
        "aura-daemon",
        "aura-ui",
        "D:\AURA\JAS",
        "vite"
    )

    try {
        $processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Name -in $processNames
            }

        foreach ($process in $processes) {
            $commandLine = [string]$process.CommandLine

            if ([string]::IsNullOrWhiteSpace($commandLine)) {
                continue
            }

            $matchesAura = $false

            foreach ($marker in $auraMarkers) {
                if ($commandLine.IndexOf(
                    $marker,
                    [System.StringComparison]::OrdinalIgnoreCase
                ) -ge 0) {
                    $matchesAura = $true
                    break
                }
            }

            if ($matchesAura) {
                Stop-ProcessTreeSafe -ProcessId ([int]$process.ProcessId)
            }
        }
    }
    catch {
    }

    Start-Sleep -Milliseconds 300

    try {
        $processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Name -in $processNames
            }

        foreach ($process in $processes) {
            $commandLine = [string]$process.CommandLine

            if ([string]::IsNullOrWhiteSpace($commandLine)) {
                continue
            }

            $matchesAura = $false

            foreach ($marker in $auraMarkers) {
                if ($commandLine.IndexOf(
                    $marker,
                    [System.StringComparison]::OrdinalIgnoreCase
                ) -ge 0) {
                    $matchesAura = $true
                    break
                }
            }

            if ($matchesAura) {
                Stop-ProcessTreeSafe -ProcessId ([int]$process.ProcessId)
            }
        }
    }
    catch {
    }
}

function Stop-PortOwner {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    try {
        $connections = Get-NetTCPConnection `
            -LocalPort $Port `
            -State Listen `
            -ErrorAction SilentlyContinue

        foreach ($connection in $connections) {
            $ownerProcessId = [int]$connection.OwningProcess

            if ($ownerProcessId -gt 0) {
                Stop-ProcessTreeSafe -ProcessId $ownerProcessId
            }
        }
    }
    catch {
    }

    try {
        $lines = netstat.exe -ano -p TCP 2>$null

        foreach ($line in $lines) {
            if ($line -notmatch "LISTENING") {
                continue
            }

            $parts = $line -split "\s+"

            if ($parts.Count -lt 5) {
                continue
            }

            $localAddress = $parts[1]
            $processIdText = $parts[$parts.Count - 1]

            if ($localAddress -notmatch ":$Port$") {
                continue
            }

            $ownerProcessId = 0

            if ([int]::TryParse(
                $processIdText,
                [ref]$ownerProcessId
            )) {
                if ($ownerProcessId -gt 0) {
                    Stop-ProcessTreeSafe -ProcessId $ownerProcessId
                }
            }
        }
    }
    catch {
    }
}

function Reset-LogFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    try {
        if (Test-Path $Path) {
            Remove-Item $Path -Force -ErrorAction SilentlyContinue
        }

        New-Item -ItemType File -Path $Path -Force | Out-Null
    }
    catch {
    }
}

function Read-LogSafe {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path $Path)) {
        return ""
    }

    try {
        return [System.IO.File]::ReadAllText($Path)
    }
    catch {
        return ""
    }
}

function Show-LauncherError {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    Add-Type -AssemblyName System.Windows.Forms

    [System.Windows.Forms.MessageBox]::Show(
        $Message,
        "AURA",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
}

function Wait-ForHttp {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,

        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest `
                -Uri $Url `
                -Method GET `
                -UseBasicParsing `
                -TimeoutSec 2 `
                -ErrorAction Stop

            if (
                $response.StatusCode -ge 200 -and
                $response.StatusCode -lt 500
            ) {
                return $true
            }
        }
        catch {
        }

        Start-Sleep -Milliseconds 500
    }

    return $false
}

function Wait-ForProcessAlive {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ProcessId,

        [int]$TimeoutSeconds = 10
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    while ((Get-Date) -lt $deadline) {
        try {
            $process = Get-Process `
                -Id $ProcessId `
                -ErrorAction SilentlyContinue

            if ($null -ne $process) {
                return $true
            }
        }
        catch {
        }

        Start-Sleep -Milliseconds 250
    }

    return $false
}

function Find-Python {
    $candidates = @(
        (Join-Path $Core ".venv\Scripts\python.exe"),
        (Join-Path $Root ".venv\Scripts\python.exe"),
        (Join-Path $Core "venv\Scripts\python.exe"),
        (Join-Path $Root "venv\Scripts\python.exe")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $command = Get-Command python.exe -ErrorAction SilentlyContinue

    if ($null -ne $command) {
        return $command.Source
    }

    return $null
}

function Find-Npm {
    $command = Get-Command npm.cmd -ErrorAction SilentlyContinue

    if ($null -ne $command) {
        return $command.Source
    }

    $command = Get-Command npm.exe -ErrorAction SilentlyContinue

    if ($null -ne $command) {
        return $command.Source
    }

    return $null
}

function Start-Core {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Python
    )

    Reset-LogFile -Path $CoreLogOut
    Reset-LogFile -Path $CoreLogErr

    $coreCommand = '""' + $Python + '" -m aura_core > "' + $CoreLogOut + '" 2> "' + $CoreLogErr + '""'

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "cmd.exe"
    $psi.Arguments = "/d /s /c $coreCommand"
    $psi.WorkingDirectory = $Core
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi

    if (-not $process.Start()) {
        throw "AURA Core process could not be started."
    }

    return $process
}

function Start-Ui {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Npm
    )

    Reset-LogFile -Path $UiLogOut
    Reset-LogFile -Path $UiLogErr

    $uiCommand = '""' + $Npm + '" run preview -- --host 127.0.0.1 --port 4173 --strictPort > "' + $UiLogOut + '" 2> "' + $UiLogErr + '""'

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "cmd.exe"
    $psi.Arguments = "/d /s /c $uiCommand"
    $psi.WorkingDirectory = $Ui
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi

    if (-not $process.Start()) {
        throw "AURA UI process could not be started."
    }

    return $process
}

function Show-Splash {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $form = New-Object System.Windows.Forms.Form
    $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
    $form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
    $form.Width = 560
    $form.Height = 300
    $form.BackColor = [System.Drawing.Color]::Black
    $form.TopMost = $true
    $form.ShowInTaskbar = $false

    $title = New-Object System.Windows.Forms.Label
    $title.Text = "AURA"
    $title.AutoSize = $true
    $title.Font = New-Object System.Drawing.Font(
        "Segoe UI",
        38,
        [System.Drawing.FontStyle]::Bold
    )
    $title.ForeColor = [System.Drawing.Color]::White
    $title.Location = New-Object System.Drawing.Point(215, 70)

    $status = New-Object System.Windows.Forms.Label
    $status.Text = "INITIALIZING CORE..."
    $status.AutoSize = $true
    $status.Font = New-Object System.Drawing.Font(
        "Consolas",
        11,
        [System.Drawing.FontStyle]::Regular
    )
    $status.ForeColor = [System.Drawing.Color]::White
    $status.Location = New-Object System.Drawing.Point(175, 155)

    $bar = New-Object System.Windows.Forms.ProgressBar
    $bar.Style = [System.Windows.Forms.ProgressBarStyle]::Marquee
    $bar.MarqueeAnimationSpeed = 25
    $bar.Width = 300
    $bar.Height = 12
    $bar.Location = New-Object System.Drawing.Point(130, 205)

    $form.Controls.Add($title)
    $form.Controls.Add($status)
    $form.Controls.Add($bar)

    $form.Show()
    $form.Refresh()

    return @{
        Form = $form
        Status = $status
    }
}

function Close-Splash {
    param(
        $Splash
    )

    if ($null -eq $Splash) {
        return
    }

    try {
        if ($null -ne $Splash.Form) {
            $Splash.Form.Close()
            $Splash.Form.Dispose()
        }
    }
    catch {
    }
}

function Open-AuraBrowser {
    $url = "http://127.0.0.1:4173/"

    $edgeCandidates = @(
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe"
    )

    foreach ($edge in $edgeCandidates) {
        if (Test-Path $edge) {
            Start-Process `
                -FilePath $edge `
                -ArgumentList "--app=$url" `
                -WindowStyle Hidden

            return
        }
    }

    $chromeCandidates = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )

    foreach ($chrome in $chromeCandidates) {
        if (Test-Path $chrome) {
            Start-Process `
                -FilePath $chrome `
                -ArgumentList "--app=$url" `
                -WindowStyle Hidden

            return
        }
    }

    Start-Process $url
}

$Python = Find-Python
$Npm = Find-Npm

if ([string]::IsNullOrWhiteSpace($Python)) {
    Show-LauncherError "Python was not found.`n`nExpected: $Core\.venv\Scripts\python.exe"
    exit 1
}

if ([string]::IsNullOrWhiteSpace($Npm)) {
    Show-LauncherError "npm was not found."
    exit 1
}

if (-not (Test-Path $Core)) {
    Show-LauncherError "AURA Core directory was not found:`n$Core"
    exit 1
}

if (-not (Test-Path $Ui)) {
    Show-LauncherError "AURA UI directory was not found:`n$Ui"
    exit 1
}

Stop-AuraRelatedProcesses
Stop-PortOwner -Port 8000
Stop-PortOwner -Port 4173

Start-Sleep -Milliseconds 700

$env:AURA_MODEL = "ollama/qwen3"
$env:AURA_LLM_MODEL = "qwen3"

$env:AURA_RESEARCH_MCP_TRANSPORT = "stdio"
$env:AURA_RESEARCH_MCP_PROVIDER_ID = "aura-research-local"
$env:AURA_RESEARCH_MCP_SERVICE_ID = "aura-local-research"
$env:AURA_RESEARCH_MCP_CAPABILITY_ID = "internet.search"
$env:AURA_RESEARCH_MCP_SEARCH_OPERATION_ID = "internet.search"
$env:AURA_RESEARCH_MCP_SEARCH_TOOL = "search"

$env:AURA_RESEARCH_MCP_FETCH_CAPABILITY_ID = "internet.search"
$env:AURA_RESEARCH_MCP_FETCH_OPERATION_ID = "internet.fetch"
$env:AURA_RESEARCH_MCP_FETCH_TOOL = "fetch"

$env:AURA_RESEARCH_MCP_COMMAND = $Python
$env:AURA_RESEARCH_MCP_ARGS = Join-Path $Core "scripts\local_research_mcp.py"

$env:AURA_EVENT_STREAM_TOKEN = "aura-dev-event-stream-token-7f3c9a2e6b1d4f8c0e5a9b7d3c1f6e2a"
$env:AURA_ALLOW_FILE_ORIGIN = "1"
$env:AURA_CORS_ORIGINS = "http://127.0.0.1:4173,http://localhost:4173"

$Splash = Show-Splash
$coreProcess = $null
$uiProcess = $null

try {
    $Splash.Status.Text = "STARTING AURA CORE..."
    $Splash.Form.Refresh()

    $coreProcess = Start-Core -Python $Python

    if (-not (Wait-ForProcessAlive -ProcessId $coreProcess.Id -TimeoutSeconds 5)) {
        $stderr = Read-LogSafe -Path $CoreLogErr
        $stdout = Read-LogSafe -Path $CoreLogOut

        $details = "AURA Core process exited before health check.`n"
        $details += "ExitCode: $($coreProcess.ExitCode)`n`n"

        if (-not [string]::IsNullOrWhiteSpace($stderr)) {
            $details += "----- aura-daemon.stderr.log -----`n"
            $details += $stderr
        }

        if (-not [string]::IsNullOrWhiteSpace($stdout)) {
            $details += "`n----- aura-daemon.stdout.log -----`n"
            $details += $stdout
        }

        throw $details
    }

    $Splash.Status.Text = "WAITING FOR CORE..."
    $Splash.Form.Refresh()

    if (-not (Wait-ForHttp -Url "http://127.0.0.1:8000/health" -TimeoutSeconds 40)) {
        $stderr = Read-LogSafe -Path $CoreLogErr
        $stdout = Read-LogSafe -Path $CoreLogOut

        $details = "AURA Core failed to start.`n`n"

        if (-not [string]::IsNullOrWhiteSpace($stderr)) {
            $details += "----- aura-daemon.stderr.log -----`n"
            $details += $stderr
        }

        if (-not [string]::IsNullOrWhiteSpace($stdout)) {
            $details += "`n----- aura-daemon.stdout.log -----`n"
            $details += $stdout
        }

        throw $details
    }

    $Splash.Status.Text = "STARTING HUD..."
    $Splash.Form.Refresh()

    $uiProcess = Start-Ui -Npm $Npm

    if (-not (Wait-ForProcessAlive -ProcessId $uiProcess.Id -TimeoutSeconds 5)) {
        $stderr = Read-LogSafe -Path $UiLogErr
        $stdout = Read-LogSafe -Path $UiLogOut

        $details = "AURA UI process exited before startup completed.`n`n"

        if (-not [string]::IsNullOrWhiteSpace($stderr)) {
            $details += "----- aura-ui.stderr.log -----`n"
            $details += $stderr
        }

        if (-not [string]::IsNullOrWhiteSpace($stdout)) {
            $details += "`n----- aura-ui.stdout.log -----`n"
            $details += $stdout
        }

        throw $details
    }

    if (-not (Wait-ForHttp -Url "http://127.0.0.1:4173/" -TimeoutSeconds 30)) {
        $stderr = Read-LogSafe -Path $UiLogErr
        $stdout = Read-LogSafe -Path $UiLogOut

        $details = "AURA HUD failed to start.`n`n"

        if (-not [string]::IsNullOrWhiteSpace($stderr)) {
            $details += "----- aura-ui.stderr.log -----`n"
            $details += $stderr
        }

        if (-not [string]::IsNullOrWhiteSpace($stdout)) {
            $details += "`n----- aura-ui.stdout.log -----`n"
            $details += $stdout
        }

        throw $details
    }

    $Splash.Status.Text = "AURA ONLINE"
    $Splash.Form.Refresh()

    Start-Sleep -Milliseconds 500

    Close-Splash -Splash $Splash
    $Splash = $null

    Open-AuraBrowser
}
catch {
    Close-Splash -Splash $Splash

    $message = $_.Exception.Message

    if ([string]::IsNullOrWhiteSpace($message)) {
        $message = "Unknown AURA startup error."
    }

    Show-LauncherError $message

    if ($null -ne $coreProcess) {
        Stop-ProcessTreeSafe -ProcessId $coreProcess.Id
    }

    if ($null -ne $uiProcess) {
        Stop-ProcessTreeSafe -ProcessId $uiProcess.Id
    }

    exit 1
}
finally {
    Close-Splash -Splash $Splash
}