# Regression on Windows PowerShell 5.1/7: JSON keys are case-sensitive.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$validator = Join-Path $root "core\scripts\validate_piper_voice_config.py"
$python = (Get-Command python -ErrorAction Stop).Source
$folder = Join-Path ([IO.Path]::GetTempPath()) ("aura-piper-config-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $folder -Force | Out-Null
try {
    $file = Join-Path $folder "turkish.onnx.json"
    # Include BOM, case-only differences and Unicode escapes, which remain
    # distinct JSON keys. This previously failed with ConvertFrom-Json.
    $json = '{"language":{"code":"tr_TR"},"phoneme_id_map":{"A":[1],"a":[2],"\u02a4":[3],"\u02a5":[4]}}'
    [IO.File]::WriteAllText($file, $json, [Text.UTF8Encoding]::new($true))
    & $python $validator $file
    if ($LASTEXITCODE -ne 0) { throw "Turkish phoneme-map config validation failed." }

    $wrong = Join-Path $folder "english.onnx.json"
    [IO.File]::WriteAllText($wrong, '{"language":{"code":"en_US"}}', [Text.UTF8Encoding]::new($false))
    $failure = Start-Process -FilePath $python -ArgumentList @($validator, $wrong) `
        -NoNewWindow -Wait -PassThru `
        -RedirectStandardError (Join-Path $folder "expected-error.log")
    if ($failure.ExitCode -eq 0) { throw "Non-Turkish model unexpectedly accepted." }

    $setup = [IO.File]::ReadAllText((Join-Path $PSScriptRoot "setup-turkish-tts.ps1"))
    if (-not $setup.Contains("validate_piper_voice_config.py")) {
        throw "Installer is not wired to the validated UTF-8 parser."
    }
    if ($setup -match '(?im)^(?!\s*#)[^\r\n]*\bConvertFrom-Json\b') {
        throw "Installer still uses case-insensitive JSON parser."
    }
    Write-Host "PASS: Piper voice JSON validation (PowerShell + Python)"
}
finally {
    Remove-Item -LiteralPath $folder -Recurse -Force -ErrorAction SilentlyContinue
}
