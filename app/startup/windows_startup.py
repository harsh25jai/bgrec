"""Windows startup: Run key + StartupApproved + Task Scheduler (reliable logon start)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app.logging.setup import get_logger
from app.utils.windows_process import no_window_creationflags

log = get_logger("startup")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_APPROVED_RUN = (
    r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
)
APP_NAME = "bgrec"
TASK_NAME = "bgrec-recorder"
# Task Manager "Enabled" state for a Run entry (see StartupApproved\Run).
STARTUP_APPROVED_ENABLED = b"\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
VBS_LAUNCHER_NAME = "bgrec-logon-start.vbs"
AUTOSTART_LOG_NAME = "autostart.log"


def format_schtasks_delay(delay_seconds: int) -> str | None:
    """mmmm:ss delay for schtasks /DELAY (ONLOGON / ONSTART / ONEVENT only)."""
    if delay_seconds <= 0:
        return None
    minutes, seconds = divmod(delay_seconds, 60)
    return f"{minutes:04d}:{seconds:02d}"


class WindowsStartupManager:
    def __init__(self, executable: Path | None = None) -> None:
        self.executable = executable or self._default_executable()
        self.last_schtasks_error: str | None = None

    @staticmethod
    def _default_executable() -> Path:
        from app.install.portable import preferred_bgrec_executable

        return preferred_bgrec_executable()

    @staticmethod
    def _schtasks_executable() -> str:
        if sys.platform == "win32":
            candidate = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "schtasks.exe"
            if candidate.is_file():
                return str(candidate)
        return "schtasks"

    @staticmethod
    def _current_run_as_user() -> str:
        user = os.environ.get("USERNAME", "")
        domain = os.environ.get("USERDOMAIN", "")
        if domain and user:
            return f"{domain}\\{user}"
        return user

    @staticmethod
    def vbs_run_command(vbs_path: Path) -> str:
        return f'wscript.exe //B //NOLOGO "{vbs_path}"'

    def _start_arguments(self) -> str:
        """Autostart: background daemon without wiping logs on every logon."""
        return "start --background --no-fresh"

    def _quoted_exe_command(self) -> str:
        exe = self.executable
        if exe.name.lower() == "bgrec.exe":
            return f'"{exe}" {self._start_arguments()}'
        import shutil

        bgrec = shutil.which("bgrec")
        if bgrec:
            return f'"{bgrec}" {self._start_arguments()}'
        return f'"{exe}" -m app.cli.main {self._start_arguments()}'

    def _autostart_log_path(self) -> Path:
        from app.config.settings import default_data_dirs

        return default_data_dirs()["logs"] / AUTOSTART_LOG_NAME

    @staticmethod
    def _interpret_startup_approved(data: bytes | None) -> str:
        if not data:
            return "missing (Run entry may still run)"
        if data.startswith(b"\x02") or data.startswith(b"\x06"):
            return "enabled"
        if data.startswith(b"\x03"):
            return "disabled (03…)"
        return f"unknown state (hex {data[:12].hex()}…)"

    def read_run_command(self) -> str | None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, APP_NAME)
                return str(value)
        except OSError:
            return None

    def read_startup_approved_status(self) -> str:
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_RUN, 0, winreg.KEY_READ
            ) as key:
                data, _ = winreg.QueryValueEx(key, APP_NAME)
                if isinstance(data, bytes):
                    return self._interpret_startup_approved(data)
                return "present (non-binary)"
        except FileNotFoundError:
            return "no entry (Run not gated by StartupApproved)"
        except OSError as exc:
            return f"unreadable ({exc})"

    def _write_hidden_launcher(self) -> Path | None:
        """
        VBS launcher runs bgrec with window style 0 (hidden).

        Avoids console flash when Windows starts a console-subsystem exe at logon.
        """
        if sys.platform != "win32":
            return None
        exe = self.executable
        if not exe.is_file():
            log.warning("Cannot write startup launcher — missing {}", exe)
            return None
        vbs_path = exe.parent / VBS_LAUNCHER_NAME
        exe_escaped = str(exe).replace('"', "")
        args = self._start_arguments()
        log_path = str(self._autostart_log_path()).replace('"', "")
        content = (
            'Set sh = CreateObject("WScript.Shell")\n'
            'Set fso = CreateObject("Scripting.FileSystemObject")\n'
            f'logPath = "{log_path}"\n'
            "Set log = fso.OpenTextFile(logPath, 8, True)\n"
            'log.WriteLine Now & " VBS launcher: begin"\n'
            f'sh.Run Chr(34) & "{exe_escaped}" & Chr(34) & " {args}", 0, False\n'
            'log.WriteLine Now & " VBS launcher: spawn issued"\n'
            "log.Close\n"
        )
        vbs_path.write_text(content, encoding="utf-8")
        return vbs_path

    def _enable_startup_approved(self) -> None:
        import winreg

        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_RUN) as key:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_BINARY, STARTUP_APPROVED_ENABLED)
            log.debug("StartupApproved enabled for {}", APP_NAME)
        except OSError as exc:
            log.warning("Could not set StartupApproved for {}: {}", APP_NAME, exc)

    def _disable_startup_approved(self) -> None:
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_RUN, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass
        except OSError:
            pass

    def _run_schtasks(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self._schtasks_executable(), *args],
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=no_window_creationflags(),
        )

    def _schtasks_failure_message(self, result: subprocess.CompletedProcess[str]) -> str:
        detail = (result.stderr or result.stdout or "").strip()
        return f"exit {result.returncode}" + (f": {detail}" if detail else "")

    def _create_logon_task(self, vbs: Path, *, delay_seconds: int = 30) -> bool:
        if sys.platform != "win32":
            return False
        self.last_schtasks_error = None
        tr = self.vbs_run_command(vbs)
        run_user = self._current_run_as_user()
        delay_token = format_schtasks_delay(delay_seconds)

        # Try with explicit /RU + /NP (current user), then simpler forms if policy blocks /DELAY or /RL.
        attempts: list[tuple[str, list[str]]] = []
        base = ["/Create", "/TN", TASK_NAME, "/TR", tr, "/SC", "ONLOGON", "/F"]
        if run_user:
            with_user = [*base, "/RU", run_user, "/NP"]
            if delay_token:
                attempts.append(("ONLOGON + delay + /RU", [*with_user, "/DELAY", delay_token]))
            attempts.append(("ONLOGON + /RU", with_user))
        if delay_token:
            attempts.append(("ONLOGON + delay", [*base, "/DELAY", delay_token]))
        attempts.append(("ONLOGON", base))

        self._delete_logon_task()
        for label, cmd in attempts:
            result = self._run_schtasks(cmd)
            if result.returncode == 0:
                log.info(
                    "Scheduled task created: {} ({}, delay={}s)",
                    TASK_NAME,
                    label,
                    delay_seconds,
                )
                return True
            msg = self._schtasks_failure_message(result)
            self.last_schtasks_error = f"{label}: {msg}"
            log.debug("schtasks {} failed — {}", label, msg)

        log.warning(
            "schtasks create failed after {} attempts. Last: {}",
            len(attempts),
            self.last_schtasks_error,
        )
        return False

    def _delete_logon_task(self) -> None:
        if sys.platform != "win32":
            return
        try:
            self._run_schtasks(["/Delete", "/TN", TASK_NAME, "/F"])
        except (OSError, subprocess.TimeoutExpired):
            pass

    def is_enabled(self) -> bool:
        import winreg

        if self._task_exists():
            return True
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
                winreg.QueryValueEx(key, APP_NAME)
                return True
        except FileNotFoundError:
            return False
        except OSError:
            return False

    def _task_exists(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            result = self._run_schtasks(["/Query", "/TN", TASK_NAME, "/FO", "LIST"])
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def enable(
        self,
        *,
        use_task: bool = True,
        use_registry: bool = True,
        logon_delay_seconds: int = 30,
    ) -> bool:
        """
        Register autostart. Returns True if Task Scheduler registration succeeded
        when use_task is True, or if use_task is False.
        """
        import winreg

        vbs = self._write_hidden_launcher()
        task_ok = not use_task
        if use_task:
            if vbs:
                task_ok = self._create_logon_task(vbs, delay_seconds=logon_delay_seconds)
            else:
                task_ok = False
                self.last_schtasks_error = "hidden launcher script could not be written"
                log.warning("Task Scheduler registration skipped — no VBS launcher")

        if use_registry:
            if vbs:
                cmd = self.vbs_run_command(vbs)
            else:
                cmd = self._quoted_exe_command()
                log.warning("Run key points at exe directly — VBS launcher missing")
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
            log.info("Startup Run key: {}", cmd)
            self._enable_startup_approved()

        return task_ok

    def disable(self) -> None:
        import winreg

        self._delete_logon_task()
        self._disable_startup_approved()
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, APP_NAME)
            log.info("Startup disabled")
        except FileNotFoundError:
            pass
        vbs = self.executable.parent / VBS_LAUNCHER_NAME
        vbs.unlink(missing_ok=True)

    def sync(self, enabled: bool) -> None:
        if enabled:
            self.enable()
        else:
            self.disable()

    def diagnostics(self) -> list[str]:
        """Human-readable checks for why autostart may not run (for status / docs)."""
        lines: list[str] = []
        if sys.platform != "win32":
            return ["Windows startup is only supported on Windows."]
        run_cmd = self.read_run_command()
        lines.append(f"Run command: {run_cmd or '(missing)'}")
        if run_cmd and "wscript.exe" not in run_cmd.lower():
            lines.append("Run key should use wscript.exe + VBS (re-run install-startup)")
        lines.append(f"StartupApproved\\Run\\bgrec: {self.read_startup_approved_status()}")
        task_present = self._task_exists()
        lines.append(f"Scheduled task '{TASK_NAME}': {'present' if task_present else 'missing'}")
        if not task_present and self.last_schtasks_error:
            lines.append(f"Last schtasks error: {self.last_schtasks_error}")
        vbs = self.executable.parent / VBS_LAUNCHER_NAME
        lines.append(f"Hidden launcher script: {vbs.is_file()}")
        lines.append(f"Executable exists: {self.executable.is_file()}")
        log_path = self._autostart_log_path()
        if log_path.is_file():
            lines.append(f"Last autostart.log write: {log_path.stat().st_mtime}")
        else:
            lines.append("autostart.log: not created yet (logon launcher never ran)")
        spawn_log = self.executable.parent.parent / "logs" / "daemon-spawn.log"
        if spawn_log.is_file():
            lines.append(f"Last daemon-spawn.log write: {spawn_log.stat().st_mtime}")
        else:
            lines.append("daemon-spawn.log: missing")
        lines.append(
            "Autostart runs at user sign-in only. Use sign-out/in to test, not lock screen."
        )
        return lines
