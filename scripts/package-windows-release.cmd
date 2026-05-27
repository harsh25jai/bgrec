@echo off
setlocal EnableExtensions
REM Package bgrec.exe + portable installer into a ZIP for distribution.
REM Run from repo root or scripts\ after: python scripts\build_exe.py
REM
REM Usage:
REM   scripts\package-windows-release.cmd
REM   (double-click also works if cwd is repo root)

cd /d "%~dp0.."
set "ROOT=%CD%"
set "DIST=%ROOT%\dist"
set "EXE=%DIST%\bgrec.exe"
set "RELEASE_DIR=%DIST%\BackgroundAudioRecorder-Windows"
set "ZIP=%DIST%\BackgroundAudioRecorder-Windows.zip"

if not exist "%EXE%" (
    echo ERROR: Missing %EXE%
    echo Run first: python scripts\build_exe.py
    exit /b 1
)

if exist "%RELEASE_DIR%" rmdir /s /q "%RELEASE_DIR%"
mkdir "%RELEASE_DIR%"

copy /y "%EXE%" "%RELEASE_DIR%\" >nul
copy /y "%ROOT%\install-portable.ps1" "%RELEASE_DIR%\" >nul
copy /y "%ROOT%\install-portable.cmd" "%RELEASE_DIR%\" >nul
copy /y "%ROOT%\scripts\windows-ensure-ffmpeg.ps1" "%RELEASE_DIR%\" >nul
copy /y "%ROOT%\uninstall.ps1" "%RELEASE_DIR%\" >nul
copy /y "%ROOT%\config\config.toml.example" "%RELEASE_DIR%\" >nul
copy /y "%ROOT%\README.md" "%RELEASE_DIR%\" >nul
copy /y "%ROOT%\scripts\decrypt_recording.py" "%RELEASE_DIR%\" >nul
copy /y "%ROOT%\decrypt-recording.cmd" "%RELEASE_DIR%\" >nul

(
echo Background Audio Recorder — portable install
echo ============================================
echo.
echo 1. Unzip this folder anywhere ^(e.g. Desktop\BackgroundAudioRecorder^).
echo 2. Open Command Prompt or PowerShell here and run:
echo.
echo    install-portable.cmd
echo    OR
echo    Set-ExecutionPolicy -Scope Process Bypass
echo    .\install-portable.ps1
echo.
echo 3. Place Google OAuth credentials.json in:
echo    %%LOCALAPPDATA%%\BackgroundAudioRecorder\credentials\credentials.json
echo.
echo 4. Open a NEW terminal ^(PATH refresh^) and run:
echo.
echo    bgrec login-google
echo    bgrec start --background
echo.
echo ffmpeg is installed automatically by install-portable.cmd if missing.
) > "%RELEASE_DIR%\INSTALL.txt"

if exist "%ZIP%" del /f /q "%ZIP%"

pushd "%DIST%"
tar -caf "BackgroundAudioRecorder-Windows.zip" "BackgroundAudioRecorder-Windows"
set "TAR_ERR=%ERRORLEVEL%"
popd

if not "%TAR_ERR%"=="0" (
    echo ERROR: tar failed ^(code %TAR_ERR%^). Windows 10+ is required, or use:
    echo   scripts\package-windows-release.ps1
    exit /b %TAR_ERR%
)

echo.
echo Created: %ZIP%
exit /b 0
