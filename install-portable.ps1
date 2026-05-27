# Portable installer for pre-built bgrec.exe (no Python required on target PC)
#
# Usage:
#   .\install-portable.ps1
#   install-portable.cmd
#   .\install-portable.ps1 -SkipFfmpeg   # skip automatic ffmpeg install

param(
    [switch]$SkipFfmpeg,
    [switch]$SkipStartupPrompt
)

$ErrorActionPreference = "Stop"

$helper = Join-Path $PSScriptRoot "windows-ensure-ffmpeg.ps1"
if (-not (Test-Path $helper)) {
    $helper = Join-Path $PSScriptRoot "scripts\windows-ensure-ffmpeg.ps1"
}
if (-not (Test-Path $helper)) {
    throw "Missing windows-ensure-ffmpeg.ps1 next to this installer."
}
. $helper

$PackageRoot = $PSScriptRoot
$ExeSource = Join-Path $PackageRoot "bgrec.exe"
$InstallDir = Join-Path $env:LOCALAPPDATA "BackgroundAudioRecorder"
$BinDir = Join-Path $InstallDir "bin"
$TargetExe = Join-Path $BinDir "bgrec.exe"

Write-Host "=== Background Audio Recorder (Portable) ===" -ForegroundColor Cyan

if (-not (Test-Path $ExeSource)) {
    throw "bgrec.exe not found next to this script. Use the ZIP from the Windows build."
}

Ensure-Ffmpeg -SkipInstall:$SkipFfmpeg

New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir "recordings") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir "cache\pending") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir "logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir "credentials") | Out-Null

Copy-Item $ExeSource $TargetExe -Force

$exampleConfig = Join-Path $PackageRoot "config.toml.example"
if (-not (Test-Path $exampleConfig)) {
    $exampleConfig = Join-Path $PackageRoot "config\config.toml.example"
}
$configPath = Join-Path $InstallDir "config.toml"
if ((Test-Path $exampleConfig) -and -not (Test-Path $configPath)) {
    Copy-Item $exampleConfig $configPath
}

# Legacy install.ps1 drops bgrec.cmd in $InstallDir; that wins over bin\bgrec.exe on PATH.
$legacyCmd = Join-Path $InstallDir "bgrec.cmd"
if (Test-Path $legacyCmd) {
    Remove-Item $legacyCmd -Force
    Write-Host "Removed legacy bgrec.cmd (script launcher)" -ForegroundColor Yellow
}

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$pathParts = @()
if ($userPath) {
    $pathParts = $userPath -split ";" | Where-Object { $_ -and ($_ -ne $InstallDir) }
}
if ($pathParts -notcontains $BinDir) {
    $pathParts = @($BinDir) + @($pathParts)
}
$newPath = ($pathParts -join ";").Trim(";")
[Environment]::SetEnvironmentVariable("Path", $newPath, "User")
Refresh-SessionPath
Write-Host "PATH: $BinDir is first for bgrec.exe" -ForegroundColor Green
Write-Host "Open a new terminal for 'bgrec' to be recognized." -ForegroundColor Yellow

Write-Host ""
Write-Host "Installed to: $TargetExe" -ForegroundColor Green
Write-Host "Next (new terminal):" -ForegroundColor Cyan
Write-Host "  bgrec login-google"
Write-Host "  bgrec start --background"
Write-Host ""

if (-not $SkipStartupPrompt) {
    $addStartup = Read-Host "Add to Windows startup now? (y/N)"
    if ($addStartup -eq "y" -or $addStartup -eq "Y") {
        & $TargetExe install-startup
        if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
            Write-Host "install-startup returned exit code $LASTEXITCODE" -ForegroundColor Yellow
        }
    }
}

Write-Host "Done." -ForegroundColor Green
