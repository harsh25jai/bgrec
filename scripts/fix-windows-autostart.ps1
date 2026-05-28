# Fix bgrec not starting at Windows logon (works on current + new builds).
# Run in PowerShell (no admin required for current user):
#   powershell -ExecutionPolicy Bypass -File scripts\fix-windows-autostart.ps1

$ErrorActionPreference = "Stop"

$BinExe = Join-Path $env:LOCALAPPDATA "bgrec\bin\bgrec.exe"
$LogDir = Join-Path $env:LOCALAPPDATA "bgrec\logs"
$VbsPath = Join-Path $env:LOCALAPPDATA "bgrec\bin\bgrec-logon-start.vbs"
$AutoLog = Join-Path $LogDir "autostart.log"
$TaskName = "bgrec-recorder"

if (-not (Test-Path $BinExe)) {
    Write-Error "bgrec not installed at $BinExe — run install-portable.cmd first."
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$exeForVbs = $BinExe -replace '\\', '\\'

$vbs = @"
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
logPath = "$AutoLog"
Set log = fso.OpenTextFile(logPath, 8, True)
log.WriteLine Now & " fix-windows-autostart: begin"
sh.Run Chr(34) & "$exeForVbs" & Chr(34) & " start --background", 0, False
log.WriteLine Now & " fix-windows-autostart: spawn issued"
log.Close
"@

Set-Content -Path $VbsPath -Value $vbs -Encoding ASCII
Write-Host "Wrote launcher: $VbsPath" -ForegroundColor Green

# Task Scheduler (primary — more reliable than Run alone)
schtasks /Delete /TN $TaskName /F 2>$null | Out-Null
schtasks /Create /TN $TaskName `
    /TR "wscript.exe //B //NOLOGO `"$VbsPath`"" `
    /SC ONLOGON /DELAY 0000:45 /RL LIMITED /F
if ($LASTEXITCODE -ne 0) {
    Write-Warning "schtasks failed (exit $LASTEXITCODE). Try running as same user after sign-in."
} else {
    Write-Host "Scheduled task created: $TaskName (45s after logon)" -ForegroundColor Green
}

# Run key (backup) — use VBS so console exe does not flash/fail at logon
$runCmd = "wscript.exe //B //NOLOGO `"$VbsPath`""
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "bgrec" -Value $runCmd
Write-Host "Run key updated to VBS launcher" -ForegroundColor Green

# StartupApproved = enabled
$approved = [byte[]](0x02,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00)
New-Item -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run" -Force | Out-Null
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run" `
    -Name "bgrec" -Value $approved -Type Binary
Write-Host "StartupApproved set to enabled" -ForegroundColor Green

Write-Host ""
Write-Host "Test: sign out, sign in, wait 60s, then:" -ForegroundColor Cyan
Write-Host "  Get-Content `"$AutoLog`" -Tail 5"
Write-Host "  bgrec status"
Write-Host "  Get-Item `"$LogDir\daemon-spawn.log`" | Select LastWriteTime"
