$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Core = Join-Path $Root "core"; $Ui = Join-Path $Root "aura-ui"; $Logs = Join-Path $Root "logs"
New-Item -ItemType Directory -Path $Logs -Force | Out-Null
. (Join-Path $PSScriptRoot "aura-env.ps1")
. (Join-Path $PSScriptRoot "aura-app-window.ps1")
. (Join-Path $PSScriptRoot "aura-processes.ps1")
function Find-Python {
 foreach ($p in @((Join-Path $Core ".venv\Scripts\python.exe"),(Join-Path $Root ".venv\Scripts\python.exe"),(Join-Path $Core "venv\Scripts\python.exe"),(Join-Path $Root "venv\Scripts\python.exe"))) {
  if (Test-Path $p) { return $p }
 }
 return $null
}
function Wait-Http([string]$Url,[int]$Seconds,[switch]$Ready) {
 $until=(Get-Date).AddSeconds($Seconds)
 while ((Get-Date)-lt $until) {
  try { $r=Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
   if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) {
    if (-not $Ready -or ($r.Content | ConvertFrom-Json).status -eq "ready") { return $true }
   }
  } catch { }
  Start-Sleep -Milliseconds 500
 }
 return $false
}
$coreProc=$null; $uiProc=$null; $failed=$false
try {
 if (-not (Test-Path $Core) -or -not (Test-Path $Ui)) { throw "core/ or aura-ui/ missing." }
 Import-AuraEnvFile -Path (Join-Path $Core ".env.local")
 $Python=Find-Python
 if (-not $Python) { throw "Python 3.13 venv missing in core\.venv or root .venv." }
 $npm=Get-Command npm.cmd -ErrorAction SilentlyContinue
 $node=Get-Command node.exe -ErrorAction SilentlyContinue
 if (-not $npm -or -not $node) { throw "Node.js and npm.cmd are required." }
 $env:AURA_STORAGE_MODE="remote"; $env:AURA_CORE_HOST="127.0.0.1"
 Assert-AuraRemoteSettings
 if (-not $env:AURA_RUNTIME) { $env:AURA_RUNTIME="ollama" }
 if (-not $env:AURA_MODEL) { $env:AURA_MODEL="qwen3:latest" }
 if (-not $env:AURA_BACKEND_ENDPOINT) { $env:AURA_BACKEND_ENDPOINT="http://127.0.0.1:11434" }
 if (-not $env:AURA_STT_MODEL) { $env:AURA_STT_MODEL="small" }
 # Bearer credentials are server-side only; Vite's loopback proxy injects
 # them into Core requests without exposing them in browser JavaScript.
 if (-not $env:AURA_API_BEARER_TOKEN) {
  $secret=New-Object byte[] 48
  $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($secret); $env:AURA_API_BEARER_TOKEN=[Convert]::ToBase64String($secret) }
  finally { $rng.Dispose(); [Array]::Clear($secret,0,$secret.Length) }
 }
 if ($env:AURA_API_BEARER_TOKEN.Length -lt 32) { throw "AURA_API_BEARER_TOKEN must be at least 32 characters." }
 if (-not $env:AURA_API_PRINCIPAL_ID) { $env:AURA_API_PRINCIPAL_ID="local_owner" }
 $bytes=New-Object byte[] 32; $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
 try { $rng.GetBytes($bytes); $env:AURA_EVENT_STREAM_TOKEN=[Convert]::ToBase64String($bytes) }
 finally { $rng.Dispose(); [Array]::Clear($bytes,0,$bytes.Length) }
 # Never shift to new ports or proxy against a different running AURA.
 Stop-AuraStaleProcesses -Root $Root
 Start-Sleep -Milliseconds 500
 $cp=8000; $up=5173
 Assert-AuraPortAvailable -Port $cp
 Assert-AuraPortAvailable -Port $up
 $env:AURA_CORE_PORT="$cp"; $env:AURA_UI_PORT="$up"
 $env:AURA_CORS_ORIGINS="http://127.0.0.1:$up"; $env:PYTHONPATH=Join-Path $Core "src"
 $v=& $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
 if ($LASTEXITCODE -ne 0 -or $v.Trim() -ne "3.13") { throw "Python 3.13 required; found $v." }
 & $Python -c "import aura_core.main"
 if ($LASTEXITCODE -ne 0) { throw "Core import check failed." }
 Write-Host "Preparing local faster-whisper STT model (first run may download the model)..."
 & $Python (Join-Path $Core "scripts\prepare_stt.py")
 if ($LASTEXITCODE -ne 0) { throw "Local STT model preparation failed. Inspect the diagnostic above; Core was not started." }
 if (-not (Test-Path (Join-Path $Ui "node_modules"))) {
  Push-Location $Ui
  try { & $npm.Source ci --no-audit --no-fund; if ($LASTEXITCODE -ne 0) { throw "npm ci failed." } }
  finally { Pop-Location }
 }
 $co=Join-Path $Logs "aura-core.stdout.log"; $ce=Join-Path $Logs "aura-core.stderr.log"
 $uo=Join-Path $Logs "aura-ui.stdout.log"; $ue=Join-Path $Logs "aura-ui.stderr.log"
 $coreProc=Start-Process $Python -ArgumentList "-m aura_core" -WorkingDirectory $Core -PassThru -WindowStyle Hidden -RedirectStandardOutput $co -RedirectStandardError $ce
 if (-not (Wait-Http "http://127.0.0.1:$cp/api/health/live" 60)) { throw "Core liveness failed. Inspect $ce" }
 if (-not (Wait-Http "http://127.0.0.1:$cp/api/health/ready" 120 -Ready)) { throw "Remote DB/object storage readiness failed. No fallback used. Inspect Core logs." }
 $viteScript=Join-Path $Ui "node_modules/vite/bin/vite.js"
 if (-not (Test-Path -LiteralPath $viteScript)) { throw "Vite executable not found; run npm ci in aura-ui." }
 $uiProc=Start-Process $node.Source -ArgumentList @($viteScript,"--host","127.0.0.1","--port","$up","--strictPort") -WorkingDirectory $Ui -PassThru -WindowStyle Hidden -RedirectStandardOutput $uo -RedirectStandardError $ue
 if (-not (Wait-Http "http://127.0.0.1:$up/" 60)) { throw "UI readiness failed. Inspect $ue" }
 Write-Host "AURA ready: Core http://127.0.0.1:$cp  UI http://127.0.0.1:$up" -ForegroundColor Green
 Start-AuraAppWindow -Url "http://127.0.0.1:$up/"
 Write-Host "AURA supervisor active. Close the application and press Enter to stop Core and UI."
 Read-Host "Press Enter to stop AURA" | Out-Null
} catch {
 $failed=$true
 Write-Host "AURA startup failed: $($_.Exception.Message)" -ForegroundColor Red
 Write-Host "Logs: $Logs"
} finally {
 foreach ($proc in @($uiProc,$coreProc)) {
  if ($null -ne $proc) {
   Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
  }
 }
 # Cleanup any same-repository child stdio/MCP processes left behind.
 Stop-AuraStaleProcesses -Root $Root
 Write-Host "AURA Core/UI supervisor stopped."
}
if ($failed) { exit 1 }
