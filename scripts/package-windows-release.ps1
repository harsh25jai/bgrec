# Package bgrec.exe + portable installer into a ZIP for distribution.
# Run on Windows after: python scripts/build_exe.py

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Dist = Join-Path $Root "dist"
$Exe = Join-Path $Dist "bgrec.exe"
$ReleaseDir = Join-Path $Dist "BackgroundAudioRecorder-Windows"
$ZipPath = Join-Path $Dist "BackgroundAudioRecorder-Windows.zip"

if (-not (Test-Path $Exe)) {
    throw "Missing $Exe — run: python scripts\build_exe.py"
}

if (Test-Path $ReleaseDir) { Remove-Item -Recurse -Force $ReleaseDir }
New-Item -ItemType Directory -Path $ReleaseDir | Out-Null

Copy-Item $Exe $ReleaseDir
Copy-Item (Join-Path $Root "install-portable.ps1") $ReleaseDir
Copy-Item (Join-Path $Root "install-portable.cmd") $ReleaseDir
Copy-Item (Join-Path $Root "uninstall.ps1") $ReleaseDir
Copy-Item (Join-Path $Root "config\config.toml.example") $ReleaseDir
Copy-Item (Join-Path $Root "README.md") $ReleaseDir

@"
Background Audio Recorder — portable install
============================================

1. Unzip this folder anywhere (e.g. Desktop\BackgroundAudioRecorder).
2. Open Command Prompt here and run:

   install-portable.cmd

   Or in PowerShell:
   Set-ExecutionPolicy -Scope Process Bypass
   .\install-portable.ps1

3. Place Google OAuth credentials.json in:
   %LOCALAPPDATA%\BackgroundAudioRecorder\credentials\credentials.json

4. Open a NEW terminal (PATH refresh) and run:

   bgrec login-google
   bgrec start --background

Requires ffmpeg on PATH for FLAC/MP3: winget install Gyan.FFmpeg
"@ | Set-Content (Join-Path $ReleaseDir "INSTALL.txt") -Encoding UTF8

if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path (Join-Path $ReleaseDir "*") -DestinationPath $ZipPath -Force

Write-Host "Created: $ZipPath" -ForegroundColor Green
