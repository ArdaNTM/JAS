# Open the local AURA UI in a chromeless Edge/Chrome application window.
function Get-AuraAppLaunchArguments {
    param([Parameter(Mandatory = $true)][string]$Url)
    $parsed = $null
    if (-not [System.Uri]::TryCreate($Url, [System.UriKind]::Absolute, [ref]$parsed) -or
        $parsed.Scheme -ne "http" -or $parsed.Host -ne "127.0.0.1" -or
        $parsed.Port -lt 1 -or $parsed.Port -gt 65535 -or
        $parsed.AbsolutePath -ne "/" -or
        $parsed.Query.Length -gt 0 -or $parsed.Fragment.Length -gt 0) {
        throw "AURA app mode only supports http://127.0.0.1:<port>/"
    }
    return @("--app=$Url", "--new-window")
}

function Find-AuraAppBrowser {
    $candidates = @(
        (Join-Path $env:ProgramFiles "Microsoft\Edge\Application\msedge.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Microsoft\Edge\Application\msedge.exe"),
        (Join-Path $env:LOCALAPPDATA "Microsoft\Edge\Application\msedge.exe"),
        (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"),
        (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe")
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return $candidate
        }
    }
    foreach ($executable in @("msedge.exe", "chrome.exe")) {
        $command = Get-Command $executable -ErrorAction SilentlyContinue
        if ($command -and (Test-Path -LiteralPath $command.Source -PathType Leaf)) {
            return $command.Source
        }
    }
    throw "Edge/Chrome app mode browser not found. Install Microsoft Edge or Google Chrome."
}

function Start-AuraAppWindow {
    param([Parameter(Mandatory = $true)][string]$Url)
    $args = @(Get-AuraAppLaunchArguments -Url $Url)
    $browser = Find-AuraAppBrowser
    Start-Process -FilePath $browser -ArgumentList $args -ErrorAction Stop | Out-Null
}
