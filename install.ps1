#Requires -Version 5.1
<#
.SYNOPSIS
  One-script installer for Background Audio Recorder (Windows 10/11).

.DESCRIPTION
  Copy this single file to any Windows PC (or paste the one-liner from README) and run.
  It downloads the app from GitHub, creates a venv, installs dependencies, and adds `bgrec` to PATH.

  Edit $GitHubRepo below before first use, or pass: -GitHubRepo "user/repo"

.EXAMPLE
  Set-ExecutionPolicy -Scope Process Bypass
  .\install.ps1

.EXAMPLE
  .\install.ps1 -GitHubRepo "yourname/background-recorder" -InstallPython

  ffmpeg is installed automatically via winget when missing (use -SkipFfmpeg to opt out).
#>

param(
    [string]$GitHubRepo = "YOUR_GITHUB_USER/background-recorder",
    [string]$Branch = "main",
    [string]$ZipUrl = "",
    [switch]$InstallPython,
    [switch]$SkipFfmpeg,
    [switch]$SkipStartupPrompt
)

$ErrorActionPreference = "Stop"

function Import-FfmpegHelper {
    $local = Join-Path $PSScriptRoot "scripts\windows-ensure-ffmpeg.ps1"
    if (Test-Path $local) {
        . $local
        return
    }
    if ($GitHubRepo -eq "YOUR_GITHUB_USER/background-recorder" -and -not $ZipUrl) {
        throw @"
Cannot load ffmpeg installer helper.
Run from a full repo clone, or set -GitHubRepo so install.ps1 can download:
  scripts\windows-ensure-ffmpeg.ps1
"@
    }
    $url = if ($ZipUrl) {
        throw "Standalone install.ps1 with -ZipUrl requires scripts\windows-ensure-ffmpeg.ps1 beside install.ps1."
    } else {
        "https://raw.githubusercontent.com/$GitHubRepo/$Branch/scripts/windows-ensure-ffmpeg.ps1"
    }
    $dest = Join-Path $env:TEMP "bgrec-windows-ensure-ffmpeg.ps1"
    Write-Host "Downloading ffmpeg helper..." -ForegroundColor DarkGray
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
    . $dest
}

Import-FfmpegHelper
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$InstallDir = Join-Path $env:LOCALAPPDATA "BackgroundAudioRecorder"
$AppDir = Join-Path $InstallDir "app"
$VenvPath = Join-Path $InstallDir "venv"
$BinLauncher = Join-Path $InstallDir "bgrec.cmd"

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Ensure-Python {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }

    if ($py) {
        $version = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        $major, $minor = $version.Split(".")
        if ([int]$major -gt 3 -or ([int]$major -eq 3 -and [int]$minor -ge 11)) {
            Write-Host "Python $version OK." -ForegroundColor Green
            return
        }
        Write-Host "Python $version found but 3.11+ required." -ForegroundColor Yellow
    }

    if ($InstallPython) {
        Write-Step "Installing Python 3.12 via winget..."
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path", "User")
        return
    }

    throw @"
Python 3.11+ not found.

Option A — install manually: https://www.python.org/downloads/ (check 'Add to PATH')
Option B — re-run with:  .\install.ps1 -InstallPython
"@
}

function Get-ProjectRoot {
    # Running from a dev clone (repo contains requirements.txt next to this script)
    $beside = Join-Path $PSScriptRoot "requirements.txt"
    if (Test-Path $beside) {
        Write-Host "Using local source: $PSScriptRoot" -ForegroundColor Green
        return $PSScriptRoot
    }
    return $null
}

function Download-Source {
    if ($GitHubRepo -eq "YOUR_GITHUB_USER/background-recorder" -and -not $ZipUrl) {
        throw @"
Set your GitHub repo before installing:

  .\install.ps1 -GitHubRepo "your-username/background-recorder"

Or host a ZIP anywhere and pass:

  .\install.ps1 -ZipUrl "https://example.com/background-recorder.zip"
"@
    }

    $url = if ($ZipUrl) {
        $ZipUrl
    } else {
        "https://github.com/$GitHubRepo/archive/refs/heads/$Branch.zip"
    }

    Write-Step "Downloading from $url"
    $tempZip = Join-Path $env:TEMP "bar-source.zip"
    $tempDir = Join-Path $env:TEMP "bar-source-extract"
    if (Test-Path $tempDir) { Remove-Item -Recurse -Force $tempDir }
    New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

    Invoke-WebRequest -Uri $url -OutFile $tempZip -UseBasicParsing
    Expand-Archive -Path $tempZip -DestinationPath $tempDir -Force

    $extracted = Get-ChildItem -Path $tempDir -Directory | Select-Object -First 1
    if (-not $extracted) { throw "Downloaded archive was empty." }

    if (Test-Path $AppDir) { Remove-Item -Recurse -Force $AppDir }
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    Move-Item -Path $extracted.FullName -Destination $AppDir
    Remove-Item -Force $tempZip -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
    Write-Host "Source installed to: $AppDir" -ForegroundColor Green
}

function Install-App([string]$ProjectRoot) {
    Write-Step "Creating virtual environment"
    if (-not (Test-Path $VenvPath)) {
        python -m venv $VenvPath
    }
    $pip = Join-Path $VenvPath "Scripts\pip.exe"
    $pythonVenv = Join-Path $VenvPath "Scripts\python.exe"

    Write-Step "Installing Python packages"
    & $pip install --upgrade pip --quiet
    $req = Join-Path $ProjectRoot "requirements.txt"
    if (-not (Test-Path $req)) { throw "Missing requirements.txt in $ProjectRoot" }
    & $pip install -r $req --quiet
    & $pip install -e $ProjectRoot --quiet

    Write-Step "Creating data directories"
    foreach ($sub in @("recordings", "cache\pending", "logs", "credentials")) {
        New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir $sub) | Out-Null
    }

    $exampleConfig = Join-Path $ProjectRoot "config\config.toml.example"
    $configPath = Join-Path $InstallDir "config.toml"
    if ((Test-Path $exampleConfig) -and -not (Test-Path $configPath)) {
        Copy-Item $exampleConfig $configPath
    }

    @"
@echo off
"$pythonVenv" -m app.cli.main %*
"@ | Set-Content -Path $BinLauncher -Encoding ASCII

    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -notlike "*$InstallDir*") {
        $newPath = if ($userPath) { "$userPath;$InstallDir" } else { $InstallDir }
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        $env:Path = "$env:Path;$InstallDir"
        Write-Host "Added to user PATH: $InstallDir" -ForegroundColor Green
        Write-Host "Open a NEW terminal for 'bgrec' to work." -ForegroundColor Yellow
    }
}

# --- Main ---
Write-Host @"

  Background Audio Recorder — Installer
  =====================================

"@ -ForegroundColor Cyan

Ensure-Python
Write-Step "Checking ffmpeg"
Ensure-Ffmpeg -SkipInstall:$SkipFfmpeg

$projectRoot = Get-ProjectRoot
if (-not $projectRoot) {
    Download-Source
    $projectRoot = $AppDir
}

Install-App -ProjectRoot $projectRoot

Write-Host @"

  Installation complete!
  ----------------------
  Config:    $InstallDir\config.toml
  OAuth:     $InstallDir\credentials\credentials.json

  Next (new terminal):
    bgrec login-google
    bgrec list-devices
    bgrec start --background
    bgrec status

"@ -ForegroundColor Green

if (-not $SkipStartupPrompt) {
    $addStartup = Read-Host "Add to Windows startup now? (y/N)"
    if ($addStartup -eq "y" -or $addStartup -eq "Y") {
        & $BinLauncher install-startup
    }
}
