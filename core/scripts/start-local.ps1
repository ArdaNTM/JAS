# Local Windows development launcher for AURA Core.
# Generates a per-process event-stream secret when one is not supplied.
# The secret is never written to disk or printed to the terminal.

$ErrorActionPreference = "Stop"

$coreRoot = Split-Path -Parent $PSScriptRoot
Set-Location $coreRoot

if ([string]::IsNullOrWhiteSpace($env:AURA_EVENT_STREAM_TOKEN)) {
    $secretBytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($secretBytes)
        $env:AURA_EVENT_STREAM_TOKEN = [Convert]::ToBase64String($secretBytes)
    }
    finally {
        $rng.Dispose()
        [Array]::Clear($secretBytes, 0, $secretBytes.Length)
    }

    Write-Host "Generated an ephemeral AURA_EVENT_STREAM_TOKEN for this Core process."
}
elseif ($env:AURA_EVENT_STREAM_TOKEN.Length -lt 32) {
    throw "AURA_EVENT_STREAM_TOKEN must contain at least 32 characters."
}

if ([string]::IsNullOrWhiteSpace($env:AURA_MODEL)) {
    $env:AURA_MODEL = "qwen3:latest"
}

if ([string]::IsNullOrWhiteSpace($env:AURA_RUNTIME)) {
    $env:AURA_RUNTIME = "ollama"
}

if ([string]::IsNullOrWhiteSpace($env:AURA_BACKEND_ENDPOINT)) {
    $env:AURA_BACKEND_ENDPOINT = "http://127.0.0.1:11434"
}

if ([string]::IsNullOrWhiteSpace($env:AURA_CORE_HOST)) {
    $env:AURA_CORE_HOST = "127.0.0.1"
}

if ([string]::IsNullOrWhiteSpace($env:AURA_CORE_PORT)) {
    $env:AURA_CORE_PORT = "8000"
}

Write-Host "Starting AURA Core on $($env:AURA_CORE_HOST):$($env:AURA_CORE_PORT) with runtime '$($env:AURA_RUNTIME)' and model '$($env:AURA_MODEL)'."
uv run python -m aura_core
