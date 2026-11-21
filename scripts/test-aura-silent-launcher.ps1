Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Silent = Join-Path $Root "scripts\launch-aura-silent.vbs"
$Launch = Join-Path $Root "scripts\launch-aura-desktop.ps1"
$Source = [IO.File]::ReadAllText($Silent)
$LauncherSource = [IO.File]::ReadAllText($Launch)

foreach ($required in @(
    'CreateObject("WScript.Shell")',
    'WScript.ScriptFullName',
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File',
    'shell.Run command, 0, False'
)) {
    if (-not $Source.Contains($required)) { throw "Missing safe WScript setting: $required" }
}
if ($LauncherSource -notmatch 'CreateNoWindow\s*=\s*\$true') {
    throw "Core and preview launch must use CreateNoWindow"
}
if ($LauncherSource -notmatch 'Show-LauncherError') {
    throw "Launcher error MessageBox handler was removed"
}
$BrowserStart = $LauncherSource.IndexOf("function Open-AuraBrowser {")
$BrowserEnd = $LauncherSource.IndexOf("`n$Python = Find-Python", $BrowserStart)
if ($BrowserStart -lt 0 -or $BrowserEnd -le $BrowserStart) {
    throw "Browser launcher function boundary was not found"
}
$BrowserBody = $LauncherSource.Substring($BrowserStart, $BrowserEnd - $BrowserStart)
if ($BrowserBody.Contains("-WindowStyle Hidden")) {
    throw "Visible Edge/Chrome app window must not be hidden"
}

$TempDesktop = Join-Path $env:TEMP ("aura-shortcut-ci-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $TempDesktop -Force | Out-Null
try {
    & (Join-Path $PSScriptRoot "create-aura-shortcut.ps1") -Root $Root -Desktop $TempDesktop
    if (-not $?) { throw "Silent shortcut creation failed" }
    $Path = Join-Path $TempDesktop "AURA.lnk"
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($Path)
    $ExpectedScript = Join-Path $Root "scripts\launch-aura-silent.vbs"
    $ExpectedHost = Join-Path $env:SystemRoot "System32\wscript.exe"
    if ($Shortcut.TargetPath -ine $ExpectedHost) { throw "Shortcut does not target wscript.exe" }
    if ($Shortcut.Arguments -ne ("`"" + $ExpectedScript + "`"")) {
        throw "Shortcut argument does not quote silent launcher path"
    }
    # A custom icon must survive replacing an existing desktop shortcut.
    $Shortcut.IconLocation = (Join-Path $env:SystemRoot "System32\shell32.dll") + ",2"
    $Shortcut.Save()
    & (Join-Path $PSScriptRoot "create-aura-shortcut.ps1") -Root $Root -Desktop $TempDesktop
    $NewShortcut = $Shell.CreateShortcut($Path)
    if ($NewShortcut.IconLocation -ne $Shortcut.IconLocation) {
        throw "Existing AURA shortcut icon was not preserved"
    }
}
finally {
    Remove-Item -LiteralPath $TempDesktop -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host "AURA silent WScript shortcut: PASS"
