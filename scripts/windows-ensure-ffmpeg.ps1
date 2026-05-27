# Shared ffmpeg check + winget install (used by install.ps1 and install-portable.ps1).
# PowerShell 5.1 compatible (ASCII only).

function Refresh-SessionPath {
    $machine = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Test-FfmpegOnPath {
    $cmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
    return ($null -ne $cmd)
}

function Add-FfmpegToSessionPath {
    $dirs = @()
    $dirs += (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links")
    $dirs += "C:\ffmpeg\bin"
    $dirs += (Join-Path $env:ProgramFiles "ffmpeg\bin")

    $pf86 = [Environment]::GetFolderPath("ProgramFilesX86")
    if ($pf86) {
        $dirs += (Join-Path $pf86 "ffmpeg\bin")
    }

    $wingetPkg = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    if (Test-Path $wingetPkg) {
        $found = Get-ChildItem -Path $wingetPkg -Filter "ffmpeg.exe" -Recurse -ErrorAction SilentlyContinue
        foreach ($item in $found) {
            $dirs += $item.Directory.FullName
        }
    }

    foreach ($dir in $dirs) {
        if (-not $dir) { continue }
        $exe = Join-Path $dir "ffmpeg.exe"
        if (Test-Path $exe) {
            if ($env:Path -notlike "*$dir*") {
                $env:Path = "$env:Path;$dir"
            }
            return
        }
    }
}

function Ensure-Ffmpeg {
    param(
        [switch]$SkipInstall
    )

    if (Test-FfmpegOnPath) {
        Write-Host "ffmpeg: OK" -ForegroundColor Green
        return
    }

    Add-FfmpegToSessionPath
    if (Test-FfmpegOnPath) {
        Write-Host "ffmpeg: OK" -ForegroundColor Green
        return
    }

    if ($SkipInstall) {
        Write-Host "ffmpeg: not installed (skipped; recordings will stay WAV)" -ForegroundColor Yellow
        return
    }

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Host "WARNING: winget not found - cannot auto-install ffmpeg." -ForegroundColor Yellow
        Write-Host "  Install manually: winget install -e --id Gyan.FFmpeg" -ForegroundColor Yellow
        return
    }

    Write-Host "ffmpeg not found - installing via winget..." -ForegroundColor Cyan
    & winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements

    Refresh-SessionPath
    Add-FfmpegToSessionPath

    if (Test-FfmpegOnPath) {
        Write-Host "ffmpeg: OK" -ForegroundColor Green
    }
    else {
        Write-Host "ffmpeg: installed (open a new terminal if bgrec still warns)" -ForegroundColor Yellow
    }
}
