"""Windows startup integration via HKCU Run registry key (user-visible, consented)."""

from __future__ import annotations

import sys
from pathlib import Path

from app.logging.setup import get_logger

log = get_logger("startup")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "bgrec"


class WindowsStartupManager:
    def __init__(self, executable: Path | None = None) -> None:
        self.executable = executable or self._default_executable()

    @staticmethod
    def _default_executable() -> Path:
        from app.install.portable import preferred_bgrec_executable

        return preferred_bgrec_executable()

    def _command(self) -> str:
        import shutil

        exe = self.executable
        if exe.name.lower() == "bgrec.exe":
            return f'"{exe}" start --background'
        bgrec = shutil.which("bgrec")
        if bgrec:
            return f'"{bgrec}" start --background'
        if exe.suffix.lower() == ".exe" and getattr(sys, "frozen", False):
            return f'"{exe}" start --background'
        return f'"{exe}" -m app.cli.main start --background'

    def is_enabled(self) -> bool:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
                winreg.QueryValueEx(key, APP_NAME)
                return True
        except FileNotFoundError:
            return False
        except OSError:
            return False

    def enable(self) -> None:
        import winreg

        cmd = self._command()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        log.info("Startup enabled: {}", cmd)

    def disable(self) -> None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, APP_NAME)
            log.info("Startup disabled")
        except FileNotFoundError:
            pass

    def sync(self, enabled: bool) -> None:
        if enabled:
            self.enable()
        else:
            self.disable()
