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
if ($LauncherSource -notmatch '(?s)try\s*\{\s*\$Python = Find-Python') {
    throw "Hidden session must catch unhandled startup/preflight errors"
}
$BrowserStart = $LauncherSource.IndexOf("function Open-AuraBrowser {")
$BrowserEnd = $LauncherSource.IndexOf("`n`$Python = Find-Python", $BrowserStart)
if ($BrowserStart -lt 0 -or $BrowserEnd -le $BrowserStart) {
    throw "Browser launcher function boundary was not found"
}
$BrowserBody = $LauncherSource.Substring($BrowserStart, $BrowserEnd - $BrowserStart)
if ($BrowserBody.Contains("-WindowStyle Hidden")) {
    throw "Visible Edge/Chrome app window must not be hidden"
}

# The launcher's verifier requires the flag to be on during the probe,
# but failed signatures must disable activation immediately.
$VerifyCall = $LauncherSource.IndexOf('aura_core.evolution.activation_delegation --verify')
$FlagOn = $LauncherSource.LastIndexOf('$env:AURA_EVOLUTION_AUTO_ACTIVATE = "1"', $VerifyCall)
$FlagOff = $LauncherSource.IndexOf('if ($LASTEXITCODE -ne 0)', $VerifyCall)
if ($VerifyCall -lt 0 -or $FlagOn -lt 0 -or $FlagOn -gt $VerifyCall -or $FlagOff -lt $VerifyCall) {
    throw 'Signed Owner verifier must run after temporary opt-in and fail closed'
}

# Check the actual npm-generated Windows argv, not an idealized path.
. (Join-Path $PSScriptRoot 'aura-processes.ps1')
$NodePath = 'C:\Program Files\nodejs\node.exe'
$UiDir = Join-Path $Root 'aura-ui'
$Cmd = '"' + $NodePath + '" "' + $UiDir +
    '\node_modules\.bin\..\vite\bin\vite.js" preview --host 127.0.0.1 --port 4173 --strictPort'
$Proc = [pscustomobject]@{ ExecutablePath = $NodePath; CommandLine = $Cmd }
if (-not (Test-AuraOwnedProcess -Process $Proc -Root $Root)) {
    throw 'Real npm node Vite preview argv must be treated as repository-owned'
}
$Foreign = [pscustomobject]@{ ExecutablePath = $NodePath;
    CommandLine = $Cmd.Replace($UiDir, 'C:\OtherRepository\aura-ui') }
if (Test-AuraOwnedProcess -Process $Foreign -Root $Root) {
    throw 'Foreign node Vite preview must never be marked as AURA-owned'
}
$NoPreview = [pscustomobject]@{ ExecutablePath = $NodePath;
    CommandLine = $Cmd.Replace(' preview --host', ' build --host') }
if (Test-AuraOwnedProcess -Process $NoPreview -Root $Root) {
    throw 'Non-preview node process must not match the safe Vite fallback'
}
$FakeExe = [pscustomobject]@{ ExecutablePath = 'C:\Windows\System32\notepad.exe';
    CommandLine = $Cmd }
if (Test-AuraOwnedProcess -Process $FakeExe -Root $Root) {
    throw 'Only node.exe may use the repository Vite preview fallback'
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
