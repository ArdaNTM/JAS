param([switch]$EnableScreenRead)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Path = Join-Path $Root "core\.env.local"
if (-not (Test-Path -LiteralPath $Path)) {
    throw "Configure core\.env.local before enabling AURA HUD."
}
$Content = [IO.File]::ReadAllText($Path)
function Set-EnvValue([string]$Name, [string]$Value) {
    $regex = "(?m)^\s*" + [regex]::Escape($Name) + "\s*=.*$"
    $line = "$Name=$Value"
    if ([regex]::IsMatch($script:Content, $regex)) {
        $script:Content = [regex]::Replace($script:Content, $regex,
          [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $line })
    } else {
        $script:Content = $script:Content.TrimEnd() + "`r`n" + $line + "`r`n"
    }
}
Set-EnvValue "AURA_HUD_ENABLED" "1"
# ScreenRead remains disabled until the operator explicitly opts in.
if ($EnableScreenRead) {
    Set-EnvValue "AURA_SCREEN_READ_ENABLED" "1"
    Set-EnvValue "AURA_VISION_MODEL" "qwen2.5vl:3b"
    if ($Content -notmatch "(?m)^\s*AURA_APPROVAL_FINGERPRINT_KEY\s*=\s*\S+") {
        $secret = New-Object byte[] 48
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try {
            $rng.GetBytes($secret)
            Set-EnvValue "AURA_APPROVAL_FINGERPRINT_KEY" ([Convert]::ToBase64String($secret))
        } finally {
            $rng.Dispose()
            [Array]::Clear($secret, 0, $secret.Length)
        }
    }
}
[IO.File]::WriteAllText($Path, $Content, [Text.UTF8Encoding]::new($false))
Write-Host "AURA HUD configuration saved locally (no credentials printed)."
Write-Host "ScreenRead enabled: $([bool]$EnableScreenRead)"
Write-Host "Restart AURA to load the new capabilities."
