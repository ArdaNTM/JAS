[CmdletBinding()]
param(
    [string]$Root = "D:\AURA\JAS",
    [switch]$StartContainers
)

$ErrorActionPreference = "Stop"
$results = [System.Collections.Generic.List[object]]::new()

function Add-Result([string]$Name, [string]$Status, [string]$Detail) {
    $results.Add([pscustomobject]@{ Check = $Name; Status = $Status; Detail = $Detail })
}

function Test-Command([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Run-Pass([string]$Name, [scriptblock]$Action) {
    try { & $Action; Add-Result $Name "PASS" "completed" }
    catch { Add-Result $Name "FAIL" $_.Exception.Message }
}

function Add-NotConfigured([string]$Name, [string]$Detail) {
    Add-Result $Name "NOT CONFIGURED" $Detail
}

$Core = Join-Path $Root "core"
$Ui = Join-Path $Root "aura-ui"
$Python = Join-Path $Core ".venv\Scripts\python.exe"
$env:PYTHONPATH = Join-Path $Core "src"
$env:AURA_MODEL = if ($env:AURA_MODEL) { $env:AURA_MODEL } else { "qwen3:4b-instruct-2507-q4_K_M" }
$env:AURA_OLLAMA_MODEL = if ($env:AURA_OLLAMA_MODEL) { $env:AURA_OLLAMA_MODEL } else { $env:AURA_MODEL }
$env:AURA_ALLOW_FILE_ORIGIN = "1"
if ([string]::IsNullOrWhiteSpace($env:AURA_EVENT_STREAM_TOKEN)) {
    # Ephemeral smoke-test ticket secret; it is never persisted or reported.
    $env:AURA_EVENT_STREAM_TOKEN = [Guid]::NewGuid().ToString("N")
}

if (-not (Test-Path $Root) -or -not (Test-Path $Core) -or -not (Test-Path $Ui)) {
    throw "AURA project layout was not found under $Root"
}

$pythonReady = $false
if (Test-Path $Python) {
    try {
        & $Python --version | Out-Null
        if ($LASTEXITCODE -eq 0) { $pythonReady = $true }
    } catch { }
}
if (-not $pythonReady) {
    Add-Result "Python environment" "BLOCKED" "core/.venv is unavailable; recreate it with a working CPython 3.13.14, then run uv sync --all-groups."
}

if ($StartContainers) {
    if (Test-Command docker) {
        if (-not $env:AURA_POSTGRES_PASSWORD) {
            Add-NotConfigured "Container startup" "AURA_POSTGRES_PASSWORD is required by docker-compose.yml."
        } else {
            Run-Pass "Container startup" { docker compose -f (Join-Path $Core "deployment\docker-compose.yml") up -d postgres qdrant }
        }
    } else { Add-Result "Container startup" "BLOCKED" "Docker CLI is not installed." }
}

if ($pythonReady) {
    Run-Pass "Python compile" { & $Python -m compileall -q (Join-Path $Core "src"); if ($LASTEXITCODE) { throw "compileall failed" } }
    Run-Pass "Python tests" { Push-Location $Core; try { & $Python -m pytest -q; if ($LASTEXITCODE) { throw "pytest failed" } } finally { Pop-Location } }
    Run-Pass "Diagnostics CLI" { & $Python (Join-Path $Core "scripts\aura_diagnostics.py") | Out-Null; if ($LASTEXITCODE) { throw "diagnostics CLI failed" } }
}

Run-Pass "Frontend build" { Push-Location $Ui; try { npm run build; if ($LASTEXITCODE) { throw "frontend build failed" } } finally { Pop-Location } }

if ($pythonReady) {
    $server = $null
    try {
        $server = Start-Process -FilePath $Python -ArgumentList @("-m", "uvicorn", "aura_core.main:app", "--host", "127.0.0.1", "--port", "8765") -WorkingDirectory $Core -PassThru -WindowStyle Hidden
        $deadline = (Get-Date).AddSeconds(30)
        do { Start-Sleep -Milliseconds 300; try { $live = Invoke-RestMethod "http://127.0.0.1:8765/api/health/live" -TimeoutSec 2; $apiReady = $live.status -eq "ok" } catch { $apiReady = $false } } while (-not $apiReady -and (Get-Date) -lt $deadline)
        if (-not $apiReady) { throw "Backend did not answer /api/health/live within 30 seconds" }
        Run-Pass "Backend live HTTP" { foreach ($path in "/api/health", "/api/health/live", "/api/diagnostics/providers") { Invoke-RestMethod "http://127.0.0.1:8765$path" -TimeoutSec 5 | Out-Null } }
        Run-Pass "WebSocket live events" {
            $ticket = (Invoke-RestMethod "http://127.0.0.1:8765/api/ws/ticket" -Method Post -TimeoutSec 5).ticket
            $node = 'const t=process.argv[1];const w=new WebSocket(`ws://127.0.0.1:8765/api/ws/events?ticket=${encodeURIComponent(t)}`);const x=setTimeout(()=>{console.error("timeout");process.exit(1)},5000);w.onmessage=e=>{if(JSON.parse(e.data).event!=="AURA_CONNECTED")process.exit(1);clearTimeout(x);w.close();process.exit(0)};w.onerror=()=>process.exit(1);'
            node -e $node $ticket
            if ($LASTEXITCODE) { throw "WebSocket handshake/event failed" }
        }
    } catch { Add-Result "Backend / WebSocket runtime" "FAIL" $_.Exception.Message }
    finally { if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -Force } }
}

if ($env:AURA_OLLAMA_URL) { $ollamaUrl = $env:AURA_OLLAMA_URL } else { $ollamaUrl = "http://127.0.0.1:11434" }
Run-Pass "Ollama Qwen3 inference" {
    $body = @{ model = $env:AURA_OLLAMA_MODEL; prompt = "Reply with exactly AURA_SMOKE_OK"; stream = $false } | ConvertTo-Json
    $reply = Invoke-RestMethod "$($ollamaUrl.TrimEnd('/'))/api/generate" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 120
    if ([string]::IsNullOrWhiteSpace($reply.response)) { throw "Ollama returned no response" }
}

if ($env:AURA_POSTGRES_DSN) {
    if ($pythonReady) { Run-Pass "PostgreSQL real connection" { & $Python -c 'import asyncio,os,asyncpg; exec("async def main():\n    connection=await asyncpg.connect(os.environ[\"AURA_POSTGRES_DSN\"])\n    try:\n        print(await connection.fetchval(\"SELECT 1\"))\n    finally:\n        await connection.close()\nasyncio.run(main())")'; if ($LASTEXITCODE) { throw "PostgreSQL SELECT 1 failed" } } }
} else { Add-NotConfigured "PostgreSQL real connection" "Set AURA_POSTGRES_DSN, or use -StartContainers with AURA_POSTGRES_PASSWORD." }

if ($env:AURA_QDRANT_URL) {
    Run-Pass "Qdrant real connection" {
        $base = $env:AURA_QDRANT_URL.TrimEnd('/')
        $health = Invoke-RestMethod "$base/healthz" -TimeoutSec 10
        $name = "aura_smoke_$([Guid]::NewGuid().ToString('N'))"
        try {
            Invoke-RestMethod "$base/collections/$name" -Method Put -ContentType "application/json" -Body '{"vectors":{"size":4,"distance":"Cosine"}}' -TimeoutSec 10 | Out-Null
            Invoke-RestMethod "$base/collections/$name/points" -Method Put -ContentType "application/json" -Body '{"points":[{"id":1,"vector":[0.1,0.2,0.3,0.4]}]}' -TimeoutSec 10 | Out-Null
        } finally { Invoke-RestMethod "$base/collections/$name" -Method Delete -TimeoutSec 10 | Out-Null }
    }
} else { Add-NotConfigured "Qdrant real connection" "Set AURA_QDRANT_URL, or use -StartContainers." }

if ($env:AURA_INTERNET_SMOKE_URL) { Run-Pass "Internet capability provider" { Invoke-WebRequest $env:AURA_INTERNET_SMOKE_URL -UseBasicParsing -TimeoutSec 15 | Out-Null } } else { Add-NotConfigured "Internet capability provider" "Set AURA_INTERNET_SMOKE_URL to an approved provider health URL." }
if ($env:AURA_CAPABILITY_FILE_ROOT) { Run-Pass "File capability provider" { $p = Join-Path $env:AURA_CAPABILITY_FILE_ROOT ("aura-smoke-" + [Guid]::NewGuid().ToString('N') + '.txt'); try { [IO.File]::WriteAllText($p, 'AURA_SMOKE_OK'); if ([IO.File]::ReadAllText($p) -ne 'AURA_SMOKE_OK') { throw 'readback mismatch' } } finally { if (Test-Path $p) { Remove-Item -LiteralPath $p } } } } else { Add-NotConfigured "File capability provider" "Set AURA_CAPABILITY_FILE_ROOT to an approved writable provider workspace." }
if ($env:AURA_BROWSER_PROVIDER_HEALTH_URL) { Run-Pass "Browser capability provider" { Invoke-WebRequest $env:AURA_BROWSER_PROVIDER_HEALTH_URL -UseBasicParsing -TimeoutSec 15 | Out-Null } } else { Add-NotConfigured "Browser capability provider" "Set AURA_BROWSER_PROVIDER_HEALTH_URL for the deployed browser/MCP provider." }

if ($env:OPENAI_API_KEY) { Run-Pass "OpenAI provider smoke" { $base = if ($env:OPENAI_BASE_URL) { $env:OPENAI_BASE_URL.TrimEnd('/') } else { 'https://api.openai.com/v1' }; Invoke-WebRequest "$base/models" -Headers @{ Authorization = "Bearer $env:OPENAI_API_KEY" } -UseBasicParsing -TimeoutSec 20 | Out-Null } } else { Add-NotConfigured "OpenAI provider smoke" "OPENAI_API_KEY is absent; provider remains optional and disabled." }

Run-Pass "Electron binary and main-process syntax" { Push-Location $Ui; try { npm exec electron -- --version; if ($LASTEXITCODE) { throw "Electron binary failed" }; node --check electron-main.cjs; if ($LASTEXITCODE) { throw "Electron main syntax failed" } } finally { Pop-Location } }

if ($pythonReady) {
    $mustPass = @("Python compile", "Python tests", "Frontend build", "Backend live HTTP", "WebSocket live events", "Electron binary and main-process syntax")
    $failedRequired = $results | Where-Object { $_.Check -in $mustPass -and $_.Status -ne "PASS" }
    if ($failedRequired) { Add-Result "Release freeze" "BLOCKED" "Required build/runtime gates are not all PASS." }
    else {
        Run-Pass "Release freeze" { & $Python (Join-Path $Core "scripts\generate_final_lock.py"); if ($LASTEXITCODE) { throw "lock generation failed" }; & $Python (Join-Path $Core "scripts\verify_final_lock.py"); if ($LASTEXITCODE) { throw "lock verification failed" }; & $Python (Join-Path $Core "scripts\verify_release_lock.py"); if ($LASTEXITCODE) { throw "release input verification failed" } }
    }
} else { Add-Result "Release freeze" "BLOCKED" "Python environment is unavailable." }

$results | Format-Table -AutoSize
if ($results.Status -contains "FAIL") { exit 1 }
