$ErrorActionPreference = "Stop"

$Root = "D:\AURA\JAS"

# AURA_D_DRIVE_RUNTIME_ENV
$AuraRuntimeRoot = Join-Path $Root ".cache"
$AuraTempRoot = Join-Path $Root ".tmp"
$AuraModelRoot = Join-Path $Root "models"

$env:TEMP = $AuraTempRoot
$env:TMP = $AuraTempRoot

$env:UV_CACHE_DIR = Join-Path $AuraRuntimeRoot "uv"
$env:PIP_CACHE_DIR = Join-Path $AuraRuntimeRoot "pip"

$env:XDG_CACHE_HOME = Join-Path $AuraRuntimeRoot "xdg"
$env:HF_HOME = Join-Path $AuraRuntimeRoot "huggingface"
$env:TORCH_HOME = Join-Path $AuraRuntimeRoot "torch"
$env:TRITON_CACHE_DIR = Join-Path $AuraRuntimeRoot "triton"

# Ollama model konumu: yalnızca bu betikten başlatılan süreçlere aktarılır.
$env:OLLAMA_MODELS = [Environment]::GetEnvironmentVariable("OLLAMA_MODELS", "User")

if ([string]::IsNullOrWhiteSpace($env:OLLAMA_MODELS)) {
    $env:OLLAMA_MODELS = "D:\AI\Models\Ollama\models"
}

@(
    $AuraRuntimeRoot,
    (Join-Path $AuraRuntimeRoot "uv"),
    (Join-Path $AuraRuntimeRoot "pip"),
    (Join-Path $AuraRuntimeRoot "xdg"),
    (Join-Path $AuraRuntimeRoot "huggingface"),
    (Join-Path $AuraRuntimeRoot "torch"),
    (Join-Path $AuraRuntimeRoot "triton"),
    $AuraTempRoot,
    (Join-Path $Root "logs"),
    (Join-Path $Root "downloads"),
    $AuraModelRoot,
    (Join-Path $AuraModelRoot "ollama")
) | ForEach-Object {
    New-Item -ItemType Directory -Path $_ -Force | Out-Null
}

$env:TEMP = $AuraTempRoot
$env:TMP = $AuraTempRoot
$env:UV_CACHE_DIR = Join-Path $AuraRuntimeRoot "uv"
$env:PIP_CACHE_DIR = Join-Path $AuraRuntimeRoot "pip"
$Core = Join-Path $Root "core"
$Ui = Join-Path $Root "aura-ui"

$CoreLogOut = Join-Path $Root "aura-daemon.stdout.log"
$CoreLogErr = Join-Path $Root "aura-daemon.stderr.log"
$UiLogOut = Join-Path $Root "aura-ui.stdout.log"
$UiLogErr = Join-Path $Root "aura-ui.stderr.log"
$OwnerLogOut = Join-Path $Root "aura-owner-review.stdout.log"
$OwnerLogErr = Join-Path $Root "aura-owner-review.stderr.log"
$AttestorLogOut = Join-Path $Root "aura-attestor.stdout.log"
$AttestorLogErr = Join-Path $Root "aura-attestor.stderr.log"

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

# Do not kill unrelated Node/Python processes or foreign port owners.
function Stop-AuraRelatedProcesses {
    . (Join-Path $PSScriptRoot "aura-processes.ps1")
    Stop-AuraStaleProcesses -Root $Root
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

        [int]$TimeoutSeconds = 30,
        [switch]$RequireOk
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

            if ($RequireOk) {
                if ($response.StatusCode -eq 200) { return $true }
            } elseif (
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

function Find-FreePort {
    param(
        [int]$PreferredPort
    )

    $port = $PreferredPort

    while ($true) {
        try {
            $listener = [System.Net.Sockets.TcpListener]::new(
                [System.Net.IPAddress]::Loopback,
                $port
            )

            $listener.Start()
            $listener.Stop()

            return $port
        }
        catch {
            $port++
        }
    }
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

function Start-OwnerReview {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Python
    )

    Reset-LogFile -Path $OwnerLogOut
    Reset-LogFile -Path $OwnerLogErr

    # Inert catalog review only. Protected passkey approval state belongs to
    # the separately provisioned local Owner OS principal, not AURA Core.
    $ownerCommand = '""' + $Python + '" -m aura_core.evolution.owner_control_plane_http > "' + $OwnerLogOut + '" 2> "' + $OwnerLogErr + '""'
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "cmd.exe"
    $psi.Arguments = "/d /s /c $ownerCommand"
    $psi.WorkingDirectory = $Core
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    if (-not $process.Start()) {
        throw "AURA Owner review process could not be started."
    }
    return $process
}

function Start-Attestor {
    param([Parameter(Mandatory = $true)][string]$Python)

    $privateKey = Join-Path $env:LOCALAPPDATA "AURA\AttestorKeys\sandbox-attestor.pem"
    $publicKey = Join-Path $env:AURA_EVOLUTION_ROOT "trust\sandbox-attestor.pub.pem"
    $keyPin = [Environment]::GetEnvironmentVariable("AURA_EVOLUTION_ATTESTOR_KEY_SHA256", "User")
    if ($env:AURA_EVOLUTION_AUTO_ACTIVATE -ne "1" -or
        $keyPin -notmatch '^[0-9a-f]{64}$' -or
        -not (Test-Path -LiteralPath $privateKey -PathType Leaf) -or
        -not (Test-Path -LiteralPath $publicKey -PathType Leaf)) {
        return $null
    }

    Reset-LogFile -Path $AttestorLogOut
    Reset-LogFile -Path $AttestorLogErr
    # The attestor independently validates Owner and key pins before signing.
    $env:AURA_EVOLUTION_ATTESTOR_KEY_SHA256 = $keyPin
    $command = '""' + $Python + '" -m aura_core.evolution.attestor_worker --evolution-root "' +
               $env:AURA_EVOLUTION_ROOT + '" --private-key "' + $privateKey +
               '" --watch > "' + $AttestorLogOut + '" 2> "' + $AttestorLogErr + '""'
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "cmd.exe"
    $psi.Arguments = "/d /s /c $command"
    $psi.WorkingDirectory = $Core
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    if (-not $process.Start()) { throw "AURA independent attestor could not start." }
    return $process
}

function Start-Ui {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Npm
    )

    Reset-LogFile -Path $UiLogOut
    Reset-LogFile -Path $UiLogErr

    $uiCommand = '""' + $Npm + '" run preview -- --host 127.0.0.1 --port ' + $UiPort + ' --strictPort > "' + $UiLogOut + '" 2> "' + $UiLogErr + '""'

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

function Start-UiWithRetry {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Npm,
        [int]$MaxAttempts = 1
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        Write-Host "Starting AURA HUD attempt $attempt/$MaxAttempts on port $UiPort..."
        $process = Start-Ui -Npm $Npm

        if (-not (Wait-ForProcessAlive -ProcessId $process.Id -TimeoutSeconds 5)) {
            $stderr = Read-LogSafe -Path $UiLogErr
            $stdout = Read-LogSafe -Path $UiLogOut

            if ($attempt -lt $MaxAttempts) {
                Write-Host "HUD process exited. Selecting a new port..." -ForegroundColor Yellow
                Stop-ProcessTreeSafe -ProcessId $process.Id
                $script:UiPort = Find-FreePort -PreferredPort ($UiPort + 1)
                $env:AURA_UI_PORT = "$UiPort"
                $env:AURA_CORS_ORIGINS = "http://127.0.0.1:$UiPort,http://localhost:$UiPort,http://127.0.0.1:5173,http://localhost:5173"
                continue
            }

            $details = "AURA UI process exited during startup.`n`n"
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

        if (Wait-ForHttp -Url "http://127.0.0.1:$UiPort/" -TimeoutSeconds 10) {
            return $process
        }

        $stderr = Read-LogSafe -Path $UiLogErr
        $stdout = Read-LogSafe -Path $UiLogOut
        Stop-ProcessTreeSafe -ProcessId $process.Id

        if ($attempt -lt $MaxAttempts) {
            Write-Host "HUD did not become ready on port $UiPort." -ForegroundColor Yellow
            Write-Host "Selecting another port and retrying..." -ForegroundColor Cyan
            $script:UiPort = Find-FreePort -PreferredPort ($UiPort + 1)
            $env:AURA_UI_PORT = "$UiPort"
            $env:AURA_CORS_ORIGINS = "http://127.0.0.1:$UiPort,http://localhost:$UiPort,http://127.0.0.1:5173,http://localhost:5173"
            continue
        }

        $details = "AURA HUD failed to become ready after $MaxAttempts attempts.`n`n"
        $details += "Last UI port: $UiPort`n`n"
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

    throw "AURA HUD startup retry loop ended unexpectedly."
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
    $url = "http://127.0.0.1:$UiPort/"

    $edgeCandidates = @(
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe"
    )

    foreach ($edge in $edgeCandidates) {
        if (Test-Path $edge) {
            Start-Process `
                -FilePath $edge `
                -ArgumentList "--force-device-scale-factor=1.5 --app=$url"

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
                -ArgumentList "--force-device-scale-factor=1.5 --app=$url"

            return
        }
    }

    Start-Process $url
}

# Hidden WScript sessions have no visible terminal. Cover every preflight
# exception (tokens, model discovery, ACL checks and port ownership) with the
# same graphical MessageBox used for runtime startup failures.
try {
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
Start-Sleep -Milliseconds 700
. (Join-Path $PSScriptRoot "aura-processes.ps1")
$CorePort = 8000
$UiPort = 4173
Assert-AuraPortAvailable -Port $CorePort
Assert-AuraPortAvailable -Port $UiPort
Assert-AuraPortAvailable -Port 5173

$env:AURA_CORE_HOST = "127.0.0.1"
$env:AURA_CORE_PORT = "$CorePort"
$env:AURA_UI_PORT = "$UiPort"

$env:AURA_RUNTIME = "ollama"
$env:AURA_MODEL = "ollama/qwen3"
$env:AURA_LLM_MODEL = "qwen3"
$env:AURA_BACKEND_ENDPOINT = "http://127.0.0.1:11434"
$env:AURA_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:AURA_OLLAMA_URL = "http://127.0.0.1:11434"
$env:AURA_BACKEND_TIMEOUT = "300"
$env:AURA_OLLAMA_FAST_RESPONSE = "1"
$env:AURA_ASSISTANT_AUTO_TOOLS_ENABLED = "1"
$env:AURA_SELF_DISCOVERY_ENABLED = "1"
$env:AURA_DISCOVERY_USE_RESEARCH_MCP = "1"
$env:AURA_SELF_DISCOVERY_INTERVAL_SECONDS = "3600"
$env:AURA_EVOLUTION_ROOT = if ($env:AURA_EVOLUTION_ROOT) { $env:AURA_EVOLUTION_ROOT } else { "D:\AURA\Evolution" }
$env:AURA_EVOLUTION_AUTO_STAGE = "1"
$env:AURA_EVOLUTION_MAX_ITEMS = "24"
$env:AURA_EVOLUTION_MAX_BYTES = "150000000"
$env:AURA_SELF_DISCOVERY_DB = Join-Path $env:AURA_EVOLUTION_ROOT "catalog\proposals.sqlite3"
$env:AURA_STORAGE_MODE = "local"

# AURA_AUTONOMOUS_DELEGATION_VERIFIED_ONLY
# An untrusted JSON file or the presence of a flag is NEVER approval.
# The public-key fingerprint is provisioned as a User environment setting
# by the Owner independently of the delegation document.
$env:AURA_EVOLUTION_AUTO_ACTIVATE = "0"
$ownerPin = [Environment]::GetEnvironmentVariable("AURA_EVOLUTION_DELEGATION_KEY_SHA256", "User")
if ($ownerPin -match '^[0-9a-f]{64}$') {
    $env:AURA_EVOLUTION_DELEGATION_KEY_SHA256 = $ownerPin
    try {
        & $Python -m aura_core.evolution.activation_delegation --verify --evolution-root $env:AURA_EVOLUTION_ROOT 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $env:AURA_EVOLUTION_AUTO_ACTIVATE = "1"
        }
    }
    catch {
        $env:AURA_EVOLUTION_AUTO_ACTIVATE = "0"
    }
}
$env:AURA_API_PRINCIPAL_ID = "local_owner"
$env:AURA_CHAT_MEMORY_ENABLED = "0"
$env:AURA_BACKGROUND_THINKING_ENABLED = "1"
$env:AURA_BACKGROUND_THINKING_PRINCIPAL_ID = "local_owner"
$env:AURA_REFLECTION_DB = Join-Path $env:LOCALAPPDATA "AURA\reflection.sqlite3"
$env:AURA_EVOLUTION_REVIEW_ENABLED = "0"
$env:AURA_STAGE_C_BROWSER_ENABLED = "0"

$env:AURA_RESEARCH_MCP_TRANSPORT = "stdio"
$env:AURA_RESEARCH_MCP_PROVIDER_ID = "aura-research-local"
$env:AURA_RESEARCH_MCP_SERVICE_NAME = "aura-local-research"
$env:AURA_RESEARCH_MCP_CAPABILITY_ID = "internet.search"
$env:AURA_RESEARCH_MCP_SEARCH_OPERATION_ID = "internet.search"
$env:AURA_RESEARCH_MCP_SEARCH_TOOL = "search"

$env:AURA_RESEARCH_MCP_FETCH_CAPABILITY_ID = "internet.fetch"
$env:AURA_RESEARCH_MCP_FETCH_OPERATION_ID = "internet.fetch"
$env:AURA_RESEARCH_MCP_FETCH_TOOL = "fetch"

$env:AURA_RESEARCH_MCP_COMMAND = $Python
$env:AURA_RESEARCH_MCP_ARGS = Join-Path $Core "scripts\local_research_mcp.py"

# Both Core and UI preview inherit the same process-local tokens.
# Never expose bearer credentials in VITE_ variables, arguments or logs.
function New-AuraToken {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
        return [Convert]::ToBase64String($bytes)
    } finally {
        $rng.Dispose()
        [Array]::Clear($bytes, 0, $bytes.Length)
    }
}
$env:AURA_API_BEARER_TOKEN = New-AuraToken
$env:AURA_EVENT_STREAM_TOKEN = New-AuraToken
$env:AURA_APPROVAL_FINGERPRINT_KEY = New-AuraToken

# Stage C state must pass the existing production NTFS private-ACL check.
# Failure keeps computer control disabled, never weakens PermissionEngine.
$env:AURA_STAGE_C_ENABLED = "0"
$env:AURA_SCREEN_CONTROL_ENABLED = "0"
$stageState = Join-Path $env:LOCALAPPDATA "AURA\StageC"
New-Item -ItemType Directory -Path $stageState -Force | Out-Null
$env:AURA_STAGE_C_DIRECTORY = $stageState
$env:AURA_STAGE_C_DB_PATH = Join-Path $stageState "stage-c.sqlite3"
$privateDirectoryCheck = "import os; from pathlib import Path; from aura_core.evolution.windows_owner_storage import _powershell, _HARDEN, require_private_acl; p=Path(os.environ['AURA_STAGE_C_DIRECTORY']); _powershell(_HARDEN,path=p); require_private_acl(p)"
& $Python -c $privateDirectoryCheck
if ($LASTEXITCODE -eq 0) {
    $env:AURA_SCREEN_CONTROL_ENABLED = "1"
    $env:AURA_STAGE_C_ENABLED = "1"
} else {
    Write-Warning "Stage C private NTFS state cannot be verified; remaining disabled."
}
$env:AURA_ALLOW_FILE_ORIGIN = "1"
$env:AURA_CORS_ORIGINS = "http://127.0.0.1:$UiPort,http://localhost:$UiPort,http://127.0.0.1:5173,http://localhost:5173"

function Assert-OllamaReady {
    try {
        $tags = Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
    } catch {
        $ollama = Get-Command ollama.exe -ErrorAction SilentlyContinue
        if ($null -eq $ollama) { throw "Ollama offline; ollama.exe is not on PATH." }
        Start-Process -FilePath $ollama.Source -ArgumentList "serve" -WindowStyle Hidden | Out-Null
        $tags = $null
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            Start-Sleep -Milliseconds 500
            try {
                $tags = Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 3
                break
            } catch { }
        }
        if ($null -eq $tags) { throw "Ollama did not become ready on 127.0.0.1:11434." }
    }
    $names = @($tags.models | ForEach-Object { [string]$_.name })
    $preferred = "qwen3:4b-instruct-2507-q4_K_M"
    $fallback = "qwen3:latest"
    if ($names -contains $preferred) {
        $selected = $preferred
    } elseif ($names -contains $fallback) {
        $selected = $fallback
    } else {
        throw "No supported Qwen3 model installed; run 'ollama pull qwen3'."
    }
    $env:AURA_MODEL = "ollama/$selected"
    $env:AURA_LLM_MODEL = $selected
    $env:AURA_INFERENCE_MODEL = $selected
    Write-Host "AURA Ollama model selected: $selected"

}
    Assert-OllamaReady
}
catch {
    Show-LauncherError $_.Exception.Message
    exit 1
}
$Splash = $null
$coreProcess = $null
$uiProcess = $null
$ownerProcess = $null
$attestorProcess = $null
$ownerWarning = $null

try {
    $Splash = Show-Splash
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

    if (-not (Wait-ForHttp -Url "http://127.0.0.1:$CorePort/health" -TimeoutSeconds 40)) {
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

    # Optional separate signing worker: never a reason to weaken Core startup.
    # Absence of protected keys leaves capabilities inactive.
    try {
        $attestorProcess = Start-Attestor -Python $Python
        if ($null -ne $attestorProcess -and
            -not (Wait-ForProcessAlive -ProcessId $attestorProcess.Id -TimeoutSeconds 2)) {
            throw "Independent attestor terminated during startup."
        }
    }
    catch {
        Write-Warning "Attestor unavailable; external MCPs remain pending attestation."
        if ($null -ne $attestorProcess) {
            Stop-ProcessTreeSafe -ProcessId $attestorProcess.Id
            $attestorProcess = $null
        }
    }

    $Splash.Status.Text = "STARTING OWNER REVIEW..."
    $Splash.Form.Refresh()

    try {
        # An unrelated listener must never be terminated. An occupied Owner
        # port is optional-service failure, not a reason to shut down Core.
        Assert-AuraPortAvailable -Port 8766
        $ownerProcess = Start-OwnerReview -Python $Python
        if (-not (Wait-ForProcessAlive -ProcessId $ownerProcess.Id -TimeoutSeconds 5)) {
            throw "Owner review process exited before health check."
        }
        # Force IPv4 (uvicorn binds only 127.0.0.1), require actual HTTP 200;
        # the older localhost/API probe could fail on IPv6/Host mismatch.
        if (-not (Wait-ForHttp -Url "http://127.0.0.1:8766/health" -TimeoutSeconds 15 -RequireOk)) {
            throw "Owner review 127.0.0.1:8766 failed health check."
        }
    }
    catch {
        $ownerWarning = $_.Exception.Message
        $ownerStderr = Read-LogSafe -Path $OwnerLogErr
        $ownerWarning += "`n`n----- aura-owner-review.stderr.log -----`n" + $ownerStderr
        Write-Warning "Owner review unavailable; continuing AURA Core and HUD startup."
        if ($null -ne $ownerProcess) {
            Stop-ProcessTreeSafe -ProcessId $ownerProcess.Id
            $ownerProcess = $null
        }
    }

    $Splash.Status.Text = "STARTING HUD..."
    $Splash.Form.Refresh()

    $uiProcess = Start-UiWithRetry -Npm $Npm

    $Splash.Status.Text = "AURA ONLINE"
    $Splash.Form.Refresh()

    Start-Sleep -Milliseconds 500

    Close-Splash -Splash $Splash
    $Splash = $null

    Open-AuraBrowser

    if (-not [string]::IsNullOrWhiteSpace($ownerWarning)) {
        # Display the Owner stderr diagnostics only after the HUD has opened.
        # A missing GUI MessageBox must not roll back already-running Core/UI.
        try { Show-LauncherError -Message $ownerWarning }
        catch { Write-Warning "Owner review failed; see aura-owner-review.stderr.log" }
    }
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

    if ($null -ne $ownerProcess) {
        Stop-ProcessTreeSafe -ProcessId $ownerProcess.Id
    }
    if ($null -ne $attestorProcess) {
        Stop-ProcessTreeSafe -ProcessId $attestorProcess.Id
    }

    exit 1
}
finally {
    Close-Splash -Splash $Splash
}
