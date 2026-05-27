# Portable installer for pre-built bgrec.exe (no Python required on target PC)
# Run: Set-ExecutionPolicy -Scope Process Bypass; .\install-portable.ps1

$ErrorActionPreference = "Stop"

$PackageRoot = $PSScriptRoot
$ExeSource = Join-Path $PackageRoot "bgrec.exe"
$InstallDir = Join-Path $env:LOCALAPPDATA "BackgroundAudioRecorder"
$BinDir = Join-Path $InstallDir "bin"
$TargetExe = Join-Path $BinDir "bgrec.exe"

Write-Host "=== Background Audio Recorder (Portable) ===" -ForegroundColor Cyan

if (-not (Test-Path $ExeSource)) {
    throw "bgrec.exe not found next to this script. Use the ZIP from the Windows build."
}

$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpeg) {
    Write-Host "WARNING: ffmpeg not on PATH. Install for FLAC/MP3: winget install Gyan.FFmpeg" -ForegroundColor Yellow
}

New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir "recordings") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir "cache\pending") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir "logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir "credentials") | Out-Null

Copy-Item $ExeSource $TargetExe -Force

$exampleConfig = Join-Path $PackageRoot "config.toml.example"
if (-not $exampleConfig) { $exampleConfig = Join-Path $PackageRoot "config\config.toml.example" }
$configPath = Join-Path $InstallDir "config.toml"
if ((Test-Path $exampleConfig) -and -not (Test-Path $configPath)) {
    Copy-Item $exampleConfig $configPath
}

# Add bin to user PATH
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$BinDir*") {
    $newPath = if ($userPath) { "$userPath;$BinDir" } else { $BinDir }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    $env:Path = "$env:Path;$BinDir"
    Write-Host "Added to user PATH: $BinDir" -ForegroundColor Green
    Write-Host "Open a new terminal for 'bgrec' to be recognized." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Installed to: $TargetExe" -ForegroundColor Green
Write-Host "Next: bgrec login-google  then  bgrec start --background" -ForegroundColor Cyan

$addStartup = Read-Host "Add to Windows startup now? (y/N)"
if ($addStartup -eq "y" -or $addStartup -eq "Y") {
    & $TargetExe install-startup
}
