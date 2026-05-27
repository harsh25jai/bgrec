# Portable installer for pre-built bgrec.exe (no Python required on target PC)
#
# Usage:
#   .\install-portable.ps1
#   install-portable.cmd
#   .\install-portable.ps1 -SkipFfmpeg   # skip automatic ffmpeg install

param(
    [switch]$SkipFfmpeg,
    [switch]$NoAutoStart,
    [switch]$SkipStartupRegistry
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
$InstallDir = Join-Path $env:LOCALAPPDATA "bgrec"
$BinDir = Join-Path $InstallDir "bin"
$TargetExe = Join-Path $BinDir "bgrec.exe"

Write-Host "=== bgrec (Portable) ===" -ForegroundColor Cyan

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

function Invoke-BgrecInstall {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$BgrecArgs)
    # Native exes log INFO to stderr (loguru); with $ErrorActionPreference Stop that becomes a terminating error.
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $TargetExe @BgrecArgs 2>&1 | Out-Null
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevEap
    }
}

$bundledRepo = Join-Path $PackageRoot "github-repo.txt"
if (Test-Path $bundledRepo) {
    $repo = (Get-Content $bundledRepo -Raw).Trim()
    if ($repo -and $repo -notmatch "YOUR_GITHUB" -and $repo.Contains("/")) {
        Invoke-BgrecInstall config migrate | Out-Null
        Invoke-BgrecInstall config --key update.github_repo --value $repo | Out-Null
        Write-Host "OTA: github_repo=$repo" -ForegroundColor DarkGray
    }
}

# Legacy install.ps1 drops bgrec.cmd in data dir; that wins over bin\bgrec.exe on PATH.
foreach ($dataDir in @($InstallDir, (Join-Path $env:LOCALAPPDATA "BackgroundAudioRecorder"))) {
    $legacyCmd = Join-Path $dataDir "bgrec.cmd"
    if (Test-Path $legacyCmd) {
        Remove-Item $legacyCmd -Force
        Write-Host "Removed legacy bgrec.cmd from $dataDir" -ForegroundColor Yellow
    }
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

if (-not $NoAutoStart) {
    Write-Host "`n==> Starting recorder in background..." -ForegroundColor Cyan
    Invoke-BgrecInstall start --background | Out-Null
    Start-Sleep -Seconds 4
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $statusText = (& $TargetExe status 2>&1 | Out-String)
    $ErrorActionPreference = $prevEap
    if ($statusText -match 'Working properly\s+\|\s+yes') {
        Write-Host "Recorder is running and healthy." -ForegroundColor Green
    } elseif ($statusText -match 'Running\s+\|\s+yes') {
        Write-Host "Recorder process is up but has issues - run: bgrec status" -ForegroundColor Yellow
    } else {
        Write-Host "Daemon may still be starting. Check: bgrec status" -ForegroundColor Yellow
        Write-Host "Logs: $InstallDir\logs\daemon-spawn.log" -ForegroundColor DarkGray
    }
}

if (-not $SkipStartupRegistry) {
    Write-Host "`n==> Adding to Windows startup (runs after sign-in)..." -ForegroundColor Cyan
    $startupExit = Invoke-BgrecInstall install-startup
    if ($startupExit -and $startupExit -ne 0) {
        Write-Host "install-startup returned exit code $startupExit" -ForegroundColor Yellow
    } else {
        Write-Host "Startup entry added." -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Optional: bgrec login-google  (for Drive upload)" -ForegroundColor Cyan
Write-Host "Check status: bgrec status" -ForegroundColor Cyan
Write-Host "Done." -ForegroundColor Green
