$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Core = Join-Path $Root "core"; $Ui = Join-Path $Root "aura-ui"; $Logs = Join-Path $Root "logs"
New-Item -ItemType Directory -Path $Logs -Force | Out-Null
. (Join-Path $PSScriptRoot "aura-env.ps1")
function Find-Python {
 foreach ($p in @((Join-Path $Core ".venv\Scripts\python.exe"),(Join-Path $Root ".venv\Scripts\python.exe"),(Join-Path $Core "venv\Scripts\python.exe"),(Join-Path $Root "venv\Scripts\python.exe"))) {
  if (Test-Path $p) { return $p }
 }
 return $null
}
function Free-Port([int]$Start) {
 for ($p=$Start; $p -le 65535; $p++) {
  $l=$null
  try { $l=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,$p); $l.Start(); return $p }
  catch { } finally { if ($l) { $l.Stop() } }
 }
 throw "No free loopback port."
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
try {
 if (-not (Test-Path $Core) -or -not (Test-Path $Ui)) { throw "core/ or aura-ui/ missing." }
 Import-AuraEnvFile -Path (Join-Path $Core ".env.local")
 $Python=Find-Python
 if (-not $Python) { throw "Python 3.13 venv missing in core\.venv or root .venv." }
 $npm=Get-Command npm.cmd -ErrorAction SilentlyContinue
 if (-not $npm) { throw "npm.cmd not found." }
 $env:AURA_STORAGE_MODE="remote"; $env:AURA_CORE_HOST="127.0.0.1"
 Assert-AuraRemoteSettings
 if (-not $env:AURA_RUNTIME) { $env:AURA_RUNTIME="ollama" }
 if (-not $env:AURA_MODEL) { $env:AURA_MODEL="qwen3:latest" }
 if (-not $env:AURA_BACKEND_ENDPOINT) { $env:AURA_BACKEND_ENDPOINT="http://127.0.0.1:11434" }
 $bytes=New-Object byte[] 32; $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
 try { $rng.GetBytes($bytes); $env:AURA_EVENT_STREAM_TOKEN=[Convert]::ToBase64String($bytes) }
 finally { $rng.Dispose(); [Array]::Clear($bytes,0,$bytes.Length) }
 $cp=Free-Port 8000; $up=Free-Port 5173
 $env:AURA_CORE_PORT="$cp"; $env:AURA_CORS_ORIGINS="http://127.0.0.1:$up,http://localhost:$up"; $env:PYTHONPATH=Join-Path $Core "src"
 $v=& $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
 if ($LASTEXITCODE -ne 0 -or $v.Trim() -ne "3.13") { throw "Python 3.13 required; found $v." }
 & $Python -c "import aura_core.main"
 if ($LASTEXITCODE -ne 0) { throw "Core import check failed." }
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
 $uiProc=Start-Process $npm.Source -ArgumentList @("run","dev","--","--host","127.0.0.1","--port","$up","--strictPort") -WorkingDirectory $Ui -PassThru -WindowStyle Hidden -RedirectStandardOutput $uo -RedirectStandardError $ue
 if (-not (Wait-Http "http://127.0.0.1:$up/" 60)) { throw "UI readiness failed. Inspect $ue" }
 Write-Host "AURA ready: Core http://127.0.0.1:$cp  UI http://127.0.0.1:$up" -ForegroundColor Green
 Start-Process "http://127.0.0.1:$up/"
} catch {
 Write-Host "AURA startup failed: $($_.Exception.Message)" -ForegroundColor Red
 Write-Host "Logs: $Logs"; Read-Host "Press Enter to close"; exit 1
}
