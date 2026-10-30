# AURA launcher environment reader. Windows PowerShell 5.1 and PowerShell 7.
# Keep all diagnostics key-only: env values may contain credentials.
function Import-AuraEnvFile {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "AURA configuration file missing: core\.env.local. Local fallback is disabled."
    }

    # Read UTF-8 with optional BOM explicitly; split all common newline styles.
    $utf8 = [System.Text.UTF8Encoding]::new($false, $true)
    $content = [System.IO.File]::ReadAllText((Resolve-Path -LiteralPath $Path).Path, $utf8)
    $pending = [System.Collections.Generic.Dictionary[string,string]]::new(
        [System.StringComparer]::OrdinalIgnoreCase
    )
    $number = 0
    foreach ($rawLine in ($content -split "\r\n|\n|\r")) {
        $number++
        $line = $rawLine.Trim().TrimStart([char]0xFEFF).Trim()
        if ($line.Length -eq 0 -or $line.StartsWith("#")) { continue }
        if ($line -notmatch '^AURA_') { continue } # Preserve existing AURA_-only import contract.

        $match = [regex]::Match($line, '^(AURA_[A-Z0-9_]+)\s*=\s*(.*)$')
        if (-not $match.Success) {
            throw "Malformed AURA_ setting on line $number of core\.env.local."
        }
        $key = $match.Groups[1].Value
        $value = $match.Groups[2].Value.Trim()
        if ($value.Length -ge 1 -and ($value[0] -eq '"' -or $value[0] -eq "'")) {
            $quote = $value[0]
            if ($value.Length -lt 2 -or $value[$value.Length - 1] -ne $quote) {
                throw "Unterminated quoted setting $key on line $number of core\.env.local."
            }
            $value = $value.Substring(1, $value.Length - 2)
        }
        if ($pending.ContainsKey($key)) {
            throw "Duplicate setting $key in core\.env.local."
        }
        $pending.Add($key, $value)
    }

    # Apply atomically after parsing so a malformed file never partially imports.
    foreach ($entry in $pending.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process")
    }
}

function Assert-AuraRemoteSettings {
    $invalid = [System.Collections.Generic.List[string]]::new()
    if ([string]::IsNullOrWhiteSpace($env:AURA_DATABASE_URL) -or
        $env:AURA_DATABASE_URL -notmatch '^postgresql(\+asyncpg)?://') {
        $invalid.Add("AURA_DATABASE_URL")
    }
    if ([string]::IsNullOrWhiteSpace($env:AURA_OBJECT_STORAGE_ENDPOINT)) {
        $invalid.Add("AURA_OBJECT_STORAGE_ENDPOINT")
    }
    if ([string]::IsNullOrWhiteSpace($env:AURA_OBJECT_STORAGE_BUCKET)) {
        $invalid.Add("AURA_OBJECT_STORAGE_BUCKET")
    }
    if ([string]::IsNullOrWhiteSpace($env:AURA_OBJECT_STORAGE_ACCESS_KEY) -and
        [string]::IsNullOrWhiteSpace($env:AURA_OBJECT_STORAGE_ACCESS_KEY_ID)) {
        $invalid.Add("AURA_OBJECT_STORAGE_ACCESS_KEY or AURA_OBJECT_STORAGE_ACCESS_KEY_ID")
    }
    if ([string]::IsNullOrWhiteSpace($env:AURA_OBJECT_STORAGE_SECRET_KEY) -and
        [string]::IsNullOrWhiteSpace($env:AURA_OBJECT_STORAGE_SECRET_ACCESS_KEY)) {
        $invalid.Add("AURA_OBJECT_STORAGE_SECRET_KEY or AURA_OBJECT_STORAGE_SECRET_ACCESS_KEY")
    }
    if ($invalid.Count -gt 0) {
        throw "Remote persistence settings missing/invalid: $($invalid -join ', '). Configure core\.env.local. Local fallback is disabled."
    }
}
