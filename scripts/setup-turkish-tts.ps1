# Optional, explicit local Turkish Piper installation for personal/noncommercial use.
# The tr_TR-dfki-medium model's card lists CC BY-NC-SA 4.0; never download
# it silently or assume commercial redistribution is licensed.
[CmdletBinding()]
param([switch]$AcceptVoiceLicense)

$ErrorActionPreference = "Stop"
if (-not $AcceptVoiceLicense) {
    throw "Review the Turkish dfki voice license (CC BY-NC-SA 4.0) and rerun with -AcceptVoiceLicense only if permitted."
}
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "core\.venv\Scripts\python.exe"
$envPath = Join-Path $root "core\.env.local"
if (-not (Test-Path -LiteralPath $python)) { throw "Core venv missing. Run uv sync --frozen --group dev first." }
if (-not (Test-Path -LiteralPath $envPath)) { throw "core\.env.local missing." }
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv is required." }

$dir = Join-Path (Split-Path -Parent $root) "voices\piper\tr_TR-dfki-medium"
New-Item -ItemType Directory -Path $dir -Force | Out-Null
$model = Join-Path $dir "tr_TR-dfki-medium.onnx"
$config = "$model.json"
$base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium/"
if (-not (Test-Path -LiteralPath $model)) {
    Invoke-WebRequest -Uri ($base + "tr_TR-dfki-medium.onnx") -OutFile "$model.download"
    Move-Item "$model.download" $model -Force
}
if (-not (Test-Path -LiteralPath $config)) {
    Invoke-WebRequest -Uri ($base + "tr_TR-dfki-medium.onnx.json") -OutFile "$config.download"
    Move-Item "$config.download" $config -Force
}
$metadata = Get-Content -LiteralPath $config -Raw | ConvertFrom-Json
if ($metadata.language.code -ne "tr_TR") { throw "Downloaded voice config is not Turkish." }
if ((Get-Item -LiteralPath $model).Length -lt 1000000) { throw "Downloaded ONNX model is too small." }

# uv sync re-resolves the locked environment; reinstall this optional package
# if you perform another sync. Do not modify the lock in this setup helper.
& uv pip install --python $python "piper-tts==1.8.0"
if ($LASTEXITCODE -ne 0) { throw "Could not install optional piper-tts runtime." }
& $python -c "from piper import PiperVoice; print('Piper runtime ready')"
if ($LASTEXITCODE -ne 0) { throw "Piper runtime import failed." }

$content = [IO.File]::ReadAllText($envPath)
$values = [ordered]@{
    AURA_TTS_PROVIDER = "piper"
    AURA_PIPER_MODEL_PATH = $model
    AURA_PIPER_CONFIG_PATH = $config
}
foreach ($key in $values.Keys) {
    $newLine = "$key=$($values[$key])"
    if ($content -match "(?m)^\s*$key\s*=") {
        $content = [regex]::Replace($content, "(?m)^\s*$key\s*=[^\r\n]*", $newLine)
    } else {
        $content = $content.TrimEnd() + [Environment]::NewLine + $newLine + [Environment]::NewLine
    }
}
[IO.File]::WriteAllText($envPath, $content, [Text.UTF8Encoding]::new($false))
Write-Host "Turkish Piper TTS configured. Restart AURA (MCP provider is selected at boot)."
