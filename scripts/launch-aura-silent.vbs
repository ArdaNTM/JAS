Option Explicit

Dim shell, fso, launcher, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Resolve the PowerShell launcher relative to this script; no current-directory
' dependency, even when the desktop shortcut is started from elsewhere.
launcher = fso.BuildPath(fso.GetParentFolderName(WScript.ScriptFullName), "launch-aura-desktop.ps1")
command = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & launcher & """"

' WindowStyle 0 hides the PowerShell console; False lets GUI/MessageBox live.
shell.Run command, 0, False
