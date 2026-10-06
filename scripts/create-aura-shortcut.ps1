Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root =
    "D:\AURA\JAS"

$Launcher =
    Join-Path `
        $Root `
        "scripts\launch-aura-desktop.ps1"

$Desktop =
    [Environment]::GetFolderPath("Desktop")

$ShortcutPath =
    Join-Path `
        $Desktop `
        "AURA.lnk"

$Shell =
    New-Object -ComObject WScript.Shell

$Shortcut =
    $Shell.CreateShortcut(
        $ShortcutPath
    )

$Shortcut.TargetPath =
    "powershell.exe"

$Shortcut.Arguments =
    "-NoProfile -ExecutionPolicy Bypass -File `"$Launcher`""

$Shortcut.WorkingDirectory =
    $Root

$Shortcut.WindowStyle = 7

$Shortcut.Description =
    "AURA Autonomous Intelligence"

$Shortcut.Save()

Write-Host `
    "AURA shortcut created: $ShortcutPath" `
    -ForegroundColor Green