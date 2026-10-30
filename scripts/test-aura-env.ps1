$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "aura-env.ps1")

$keys = @(
    "AURA_STORAGE_MODE", "AURA_DATABASE_URL", "AURA_OBJECT_STORAGE_ENDPOINT",
    "AURA_OBJECT_STORAGE_BUCKET", "AURA_OBJECT_STORAGE_ACCESS_KEY",
    "AURA_OBJECT_STORAGE_ACCESS_KEY_ID", "AURA_OBJECT_STORAGE_SECRET_KEY",
    "AURA_OBJECT_STORAGE_SECRET_ACCESS_KEY"
)
$previous = @{}
foreach ($key in $keys) {
    $previous[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
    [Environment]::SetEnvironmentVariable($key, $null, "Process")
}
$directory = Join-Path ([System.IO.Path]::GetTempPath()) ("aura-env-test-" + [guid]::NewGuid().ToString("N"))
New-Item -Path $directory -ItemType Directory -Force | Out-Null

function Assert-True([bool]$condition, [string]$message) {
    if (-not $condition) { throw "Assertion failed: $message" }
}
try {
    $bom = [System.Text.UTF8Encoding]::new($true)
    $withoutBom = [System.Text.UTF8Encoding]::new($false)

    # UTF-8 BOM, mixed CRLF/LF/CR, indentation, blank/comment lines, quoted values.
    $content = @(
        "   AURA_STORAGE_MODE = remote  ",
        "    # this is a comment",
        "",
        "AURA_DATABASE_URL = 'postgresql+asyncpg://aura:test@127.0.0.1:5432/aura' ",
        "  AURA_OBJECT_STORAGE_ENDPOINT = http://127.0.0.1:9000",
        "AURA_OBJECT_STORAGE_BUCKET=aura",
        ' AURA_OBJECT_STORAGE_ACCESS_KEY = "test-key" ',
        "AURA_OBJECT_STORAGE_SECRET_KEY = test-secret"
    ) -join "`r`n"
    $path = Join-Path $directory "bom.env"
    [System.IO.File]::WriteAllText($path, $content, $bom)
    Import-AuraEnvFile -Path $path
    Assert-AuraRemoteSettings
    Assert-True ($env:AURA_STORAGE_MODE -eq "remote") "BOM first setting"
    Assert-True ($env:AURA_DATABASE_URL -eq "postgresql+asyncpg://aura:test@127.0.0.1:5432/aura") "quoted PostgreSQL URL"
    Assert-True ($env:AURA_OBJECT_STORAGE_ACCESS_KEY -eq "test-key") "quoted access key"

    # BOM also tolerated after leading whitespace; CR-only and LF-only newline forms.
    $path = Join-Path $directory "mixed.env"
    [System.IO.File]::WriteAllText($path,
        (" " + [char]0xFEFF + "AURA_STORAGE_MODE=remote`r" +
        "AURA_OBJECT_STORAGE_BUCKET = alternate`n" +
        "#comment`n"), $withoutBom)
    Import-AuraEnvFile -Path $path
    Assert-True ($env:AURA_OBJECT_STORAGE_BUCKET -eq "alternate") "mixed newline parsing"

    # Invalid file must not partially modify Process environment.
    $path = Join-Path $directory "invalid.env"
    [System.IO.File]::WriteAllText($path,
        "AURA_STORAGE_MODE=changed`nAURA_DATABASE_URL:broken", $withoutBom)
    $caught = $false
    try { Import-AuraEnvFile -Path $path } catch { $caught = $true }
    Assert-True $caught "malformed AURA setting rejected"
    Assert-True ($env:AURA_STORAGE_MODE -eq "remote") "parse atomicity"

    # Fail-closed, key-only diagnostic for absent credentials.
    [Environment]::SetEnvironmentVariable("AURA_OBJECT_STORAGE_SECRET_KEY", $null, "Process")
    $message = ""
    try { Assert-AuraRemoteSettings } catch { $message = $_.Exception.Message }
    Assert-True ($message.Contains("AURA_OBJECT_STORAGE_SECRET_KEY")) "missing-key diagnostic"
    Assert-True (-not $message.Contains("test-secret")) "credentials never leaked in diagnostic"

    Write-Host "PASS: AURA Windows environment loader regression tests"
}
finally {
    foreach ($key in $keys) {
        [Environment]::SetEnvironmentVariable($key, $previous[$key], "Process")
    }
    Remove-Item -LiteralPath $directory -Recurse -Force -ErrorAction SilentlyContinue
}
