param(
    [string]$Root = "D:\AURA\JAS",
    [string]$Desktop = [Environment]::GetFolderPath("Desktop")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path -LiteralPath $Root).Path
$SilentLauncher = Join-Path $Root "scripts\launch-aura-silent.vbs"

if (-not (Test-Path -LiteralPath $SilentLauncher -PathType Leaf)) {
    throw "AURA silent launcher is missing: $SilentLauncher"
}

$WScript = Join-Path $env:SystemRoot "System32\wscript.exe"
if (-not (Test-Path -LiteralPath $WScript -PathType Leaf)) {
    throw "Windows Script Host is not installed: $WScript"
}

if (-not (Test-Path -LiteralPath $Desktop -PathType Container)) {
    throw "Desktop shortcut folder is unavailable: $Desktop"
}
$ShortcutPath = Join-Path $Desktop "AURA.lnk"

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)

# A pre-existing AURA icon is kept when only the launcher target changes.
$ExistingIcon = $Shortcut.IconLocation

$Shortcut.TargetPath = $WScript
$Shortcut.Arguments = "`"$SilentLauncher`""
$Shortcut.WorkingDirectory = $Root
$Shortcut.WindowStyle = 7
$Shortcut.Description = "AURA Autonomous Intelligence"

if (-not [string]::IsNullOrWhiteSpace($ExistingIcon)) {
    $Shortcut.IconLocation = $ExistingIcon
}
$Shortcut.Save()

Write-Host "AURA silent shortcut created: $ShortcutPath" -ForegroundColor Green
