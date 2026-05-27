@echo off
REM Decrypt a .enc file (works without rebuilding bgrec.exe if Python venv exists).
REM Usage: decrypt-recording.cmd "C:\path\to\file.flac.enc"

setlocal
set "PY=%LOCALAPPDATA%\BackgroundAudioRecorder\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

set "SCRIPT=%~dp0scripts\decrypt_recording.py"
if not exist "%SCRIPT%" set "SCRIPT=%~dp0decrypt_recording.py"

"%PY%" "%SCRIPT%" %*
exit /b %ERRORLEVEL%
