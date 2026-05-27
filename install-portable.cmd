@echo off
REM Portable installer for pre-built bgrec.exe (double-click or run from cmd).
REM Delegates to install-portable.ps1 with execution policy bypass.
REM
REM   install-portable.cmd
REM   install-portable.cmd -SkipFfmpeg
REM   install-portable.cmd -NoAutoStart -SkipStartupRegistry

setlocal EnableExtensions
cd /d "%~dp0"

if not exist "%~dp0bgrec.exe" (
    echo ERROR: bgrec.exe not found next to this script.
    echo Use the ZIP from the Windows build.
    exit /b 1
)

where powershell >nul 2>&1
if errorlevel 1 (
    echo ERROR: PowerShell is required. Run install-portable.ps1 manually.
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-portable.ps1" %*
exit /b %ERRORLEVEL%
