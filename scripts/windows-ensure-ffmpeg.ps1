# Shared ffmpeg check + winget install (used by install.ps1 and install-portable.ps1).

function Refresh-SessionPath {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User")
}

function Test-FfmpegOnPath {
    return [bool](Get-Command ffmpeg -ErrorAction SilentlyContinue)
}

function Add-FfmpegToSessionPath {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links"),
        "C:\ffmpeg\bin",
        (Join-Path $env:ProgramFiles "ffmpeg\bin"),
        (Join-Path ${env:ProgramFiles(x86)} "ffmpeg\bin")
    )
    $wingetPkg = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    if (Test-Path $wingetPkg) {
        $candidates += @(Get-ChildItem -Path $wingetPkg -Filter "ffmpeg.exe" -Recurse -ErrorAction SilentlyContinue |
            ForEach-Object { $_.Directory.FullName })
    }
    foreach ($dir in $candidates) {
        if ($dir -and (Test-Path (Join-Path $dir "ffmpeg.exe"))) {
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
        Write-Host "WARNING: winget not found — cannot auto-install ffmpeg." -ForegroundColor Yellow
        Write-Host "  Install manually: winget install -e --id Gyan.FFmpeg" -ForegroundColor Yellow
        return
    }

    Write-Host "ffmpeg not found — installing via winget..." -ForegroundColor Cyan
    & winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements

    Refresh-SessionPath
    Add-FfmpegToSessionPath

    if (Test-FfmpegOnPath) {
        Write-Host "ffmpeg: OK" -ForegroundColor Green
    } else {
        Write-Host "ffmpeg: installed (open a new terminal if bgrec still warns)" -ForegroundColor Yellow
    }
}
