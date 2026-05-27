# bgrec — uninstall script
# Run: Set-ExecutionPolicy -Scope Process Bypass; .\uninstall.ps1

$ErrorActionPreference = "Stop"

$InstallDir = Join-Path $env:LOCALAPPDATA "bgrec"
$LegacyInstallDir = Join-Path $env:LOCALAPPDATA "BackgroundAudioRecorder"
$AppDir = Join-Path $InstallDir "app"
$VenvPython = Join-Path $InstallDir "venv\Scripts\python.exe"
$LegacyVenv = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython) -and (Test-Path $LegacyVenv)) { $VenvPython = $LegacyVenv }

Write-Host "=== bgrec Uninstaller ===" -ForegroundColor Cyan

# Stop service
$PortableExe = Join-Path $InstallDir "bin\bgrec.exe"
if (Test-Path $PortableExe) {
    & $PortableExe stop 2>$null
} elseif (Test-Path $VenvPython) {
    Write-Host "Stopping background service..."
    & $VenvPython -m app.cli.main stop 2>$null
} else {
    $bgrec = Get-Command bgrec -ErrorAction SilentlyContinue
    if ($bgrec) { & bgrec stop 2>$null }
}

# Remove startup registry entry (current and legacy name)
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
foreach ($entry in @("bgrec", "BackgroundAudioRecorder")) {
    try {
        Remove-ItemProperty -Path $runKey -Name $entry -ErrorAction Stop
        Write-Host "Removed startup entry: $entry" -ForegroundColor Green
    } catch {
        # not present
    }
}

$removeData = Read-Host "Delete all local data (recordings, keys, config)? (y/N)"
if ($removeData -eq "y" -or $removeData -eq "Y") {
    foreach ($dir in @($InstallDir, $LegacyInstallDir)) {
        if (Test-Path $dir) {
            Remove-Item -Recurse -Force $dir
            Write-Host "Removed $dir" -ForegroundColor Green
        }
    }
} else {
    Write-Host "Local data kept at: $InstallDir (legacy: $LegacyInstallDir)"
}

$removeApp = Read-Host "Remove installed app source and venv under LocalAppData? (y/N)"
if ($removeApp -eq "y" -or $removeApp -eq "Y") {
    foreach ($dir in @((Join-Path $InstallDir "app"), (Join-Path $InstallDir "venv"), (Join-Path $InstallDir "bgrec.cmd"))) {
        if (Test-Path $dir) {
            Remove-Item -Recurse -Force $dir
            Write-Host "Removed $dir" -ForegroundColor Green
        }
    }
}

Write-Host "Uninstall complete." -ForegroundColor Green
