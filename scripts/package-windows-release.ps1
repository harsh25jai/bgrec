# Package bgrec.exe + portable installer into a ZIP for distribution.
# Run on Windows after: python scripts/build_exe.py
#
# Usage:
#   .\scripts\package-windows-release.ps1
#   .\scripts\package-windows-release.ps1 -Channel test -GitRef test -GitSha abc1234

param(
    [ValidateSet("release", "test")]
    [string]$Channel = "release",
    [string]$GitRef = $env:GITHUB_REF_NAME,
    [string]$GitSha = $env:GITHUB_SHA
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Dist = Join-Path $Root "dist"
$Exe = Join-Path $Dist "bgrec.exe"
$ReleaseDir = Join-Path $Dist "bgrec-Windows"
$ZipName = if ($Channel -eq "test") { "bgrec-Windows-test.zip" } else { "bgrec-Windows.zip" }
$ZipPath = Join-Path $Dist $ZipName

function Get-AppVersion {
    $pyproject = Join-Path $Root "pyproject.toml"
    if (-not (Test-Path $pyproject)) { return "0.0.0" }
    $line = Select-String -Path $pyproject -Pattern '^\s*version\s*=\s*"([^"]+)"' | Select-Object -First 1
    if ($line -and $line.Matches.Count -gt 0) { return $line.Matches[0].Groups[1].Value }
    return "0.0.0"
}

if (-not (Test-Path $Exe)) {
    throw "Missing $Exe - run: python scripts\build_exe.py"
}

if (Test-Path $ReleaseDir) { Remove-Item -Recurse -Force $ReleaseDir }
New-Item -ItemType Directory -Path $ReleaseDir | Out-Null

Copy-Item $Exe $ReleaseDir
Copy-Item (Join-Path $Root "install-portable.ps1") $ReleaseDir
Copy-Item (Join-Path $Root "install-portable.cmd") $ReleaseDir
Copy-Item (Join-Path $Root "scripts\windows-ensure-ffmpeg.ps1") $ReleaseDir
Copy-Item (Join-Path $Root "uninstall.ps1") $ReleaseDir
Copy-Item (Join-Path $Root "config\config.toml.example") $ReleaseDir
$repoFile = Join-Path $Root "config\github-repo.txt"
if (Test-Path $repoFile) {
    Copy-Item $repoFile $ReleaseDir
}
$schemaFile = Join-Path $Root "config\schema-version.txt"
if (Test-Path $schemaFile) {
    Copy-Item $schemaFile $ReleaseDir
}
Copy-Item (Join-Path $Root "README.md") $ReleaseDir
Copy-Item (Join-Path $Root "scripts\decrypt_recording.py") $ReleaseDir
Copy-Item (Join-Path $Root "decrypt-recording.cmd") $ReleaseDir

@"
bgrec — portable install
========================

1. Unzip this folder anywhere (e.g. Desktop\bgrec).
2. Open Command Prompt here and run:

   install-portable.cmd

   Or in PowerShell:
   Set-ExecutionPolicy -Scope Process Bypass
   .\install-portable.ps1

3. Place Google OAuth credentials.json in:
   %LOCALAPPDATA%\bgrec\credentials\credentials.json

4. Open a NEW terminal (PATH refresh) and run:

   bgrec login-google
   bgrec start --background

ffmpeg is installed automatically by install-portable.cmd (via winget) if missing.
"@ | Set-Content (Join-Path $ReleaseDir "INSTALL.txt") -Encoding UTF8

$version = Get-AppVersion
$buildInfo = @"
bgrec build metadata
===================
channel: $Channel
version: $version
git_ref: $(if ($GitRef) { $GitRef } else { "local" })
git_sha: $(if ($GitSha) { $GitSha } else { "local" })
built_utc: $((Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"))
"@
$buildInfo | Set-Content (Join-Path $ReleaseDir "BUILD_INFO.txt") -Encoding UTF8

if ($Channel -eq "test") {
    @"
bgrec — TEST build (not a GitHub Release)
=========================================

This ZIP is from the test branch CI. Do not use for production OTA.

Install: run install-portable.cmd (same as release builds).
See BUILD_INFO.txt for commit and version.
"@ | Set-Content (Join-Path $ReleaseDir "INSTALL-TEST.txt") -Encoding UTF8
}

if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path (Join-Path $ReleaseDir "*") -DestinationPath $ZipPath -Force

Write-Host "Created: $ZipPath (channel=$Channel, version=$version)" -ForegroundColor Green
