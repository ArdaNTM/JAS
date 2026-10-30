@echo off
setlocal
cd /d "%~dp0.." || exit /b 1
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_aura.ps1"
set "aura_exit=%errorlevel%"
if not "%aura_exit%"=="0" pause
endlocal & exit /b %aura_exit%
