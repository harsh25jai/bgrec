"""Windows autostart helpers (platform-neutral unit tests)."""

from __future__ import annotations

from pathlib import Path

from app.startup.windows_startup import WindowsStartupManager, format_schtasks_delay


def test_format_schtasks_delay() -> None:
    assert format_schtasks_delay(30) == "0000:30"
    assert format_schtasks_delay(45) == "0000:45"
    assert format_schtasks_delay(90) == "0001:30"
    assert format_schtasks_delay(0) is None


def test_vbs_run_command() -> None:
    vbs = Path(r"C:\Users\me\AppData\Local\bgrec\bin\bgrec-logon-start.vbs")
    cmd = WindowsStartupManager.vbs_run_command(vbs)
    assert cmd.startswith('wscript.exe //B //NOLOGO "')
    assert str(vbs) in cmd
