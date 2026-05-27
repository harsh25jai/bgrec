"""Background daemon process management."""

from __future__ import annotations

import enum
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from app.config.settings import load_config
from app.logging.setup import configure_logging, get_logger
from app.service.singleton import is_daemon_lock_held
from app.service.state import DaemonState

log = get_logger("daemon")


class StopResult(enum.Enum):
    STOPPED = "stopped"
    NOT_RUNNING = "not_running"
    FAILED = "failed"


def state_path() -> Path:
    cfg = load_config()
    return cfg.ensure_directories()["root"] / "state.json"


def process_image_path(pid: int) -> str | None:
    """Full path to the process executable, or None if inaccessible."""
    if pid <= 0:
        return None
    if sys.platform != "win32":
        try:
            return os.readlink(f"/proc/{pid}/exe")
        except OSError:
            return None

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32_768)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
    finally:
        kernel32.CloseHandle(handle)
    return None


def is_process_running(pid: int) -> bool:
    return process_image_path(pid) is not None


def is_bgrec_process(pid: int, expected_executable: str | None = None) -> bool:
    """True if PID looks like this app's daemon (not a recycled unrelated process)."""
    image = process_image_path(pid)
    if not image:
        return False
    if expected_executable:
        try:
            if Path(image).resolve() == Path(expected_executable).resolve():
                return True
        except OSError:
            pass
    name = Path(image).name.lower()
    if name == "bgrec.exe":
        return True
    if "bgrec" in image.replace("\\", "/").lower():
        return True
    if name.startswith("python"):
        try:
            out = subprocess.run(
                [
                    "wmic",
                    "process",
                    "where",
                    f"processid={pid}",
                    "get",
                    "commandline",
                    "/format:list",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            cmd = (out.stdout or "").lower()
            return "bgrec" in cmd or "app.cli.main" in cmd
        except (OSError, subprocess.TimeoutExpired):
            return False
    return False


def reconcile_daemon_state(state: DaemonState, path: Path) -> DaemonState:
    """
    Fix state.json when the daemon died, PID was reused, or flags disagree with reality.
    """
    changed = False
    lock_held = is_daemon_lock_held()

    if state.pid:
        alive = is_process_running(state.pid)
        ours = alive and is_bgrec_process(state.pid, state.daemon_executable)
        if not alive or not ours:
            if state.running or state.pid:
                log.debug(
                    "Clearing stale daemon state (pid={}, alive={}, ours={}, lock={})",
                    state.pid,
                    alive,
                    ours,
                    lock_held,
                )
            state.running = False
            state.pid = None
            state.daemon_executable = None
            changed = True
        elif not lock_held and state.running:
            # Process exists but mutex gone — coordinator likely crashed without cleanup
            log.debug("Daemon PID {} alive but mutex free — clearing running flag", state.pid)
            state.running = False
            changed = True
    elif state.running:
        state.running = False
        changed = True

    if not lock_held and not state.pid and state.running:
        state.running = False
        changed = True

    if changed:
        state.save(path)
    return state


def is_daemon_active(state: DaemonState | None = None) -> bool:
    """True when the real recording daemon is up (mutex + matching PID)."""
    path = state_path()
    state = reconcile_daemon_state(state or DaemonState.load(path), path)
    if not state.pid or not state.running:
        return False
    if not is_process_running(state.pid):
        return False
    if not is_bgrec_process(state.pid, state.daemon_executable):
        return False
    return is_daemon_lock_held()


def wait_for_daemon_active(timeout: float = 20.0) -> DaemonState | None:
    """
    Poll until the background daemon holds the mutex and state.json is consistent.
    PyInstaller one-file cold start often needs >2s before state is written.
    """
    path = state_path()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = reconcile_daemon_state(DaemonState.load(path), path)
        if is_daemon_active(state):
            return state
        if is_daemon_lock_held():
            time.sleep(0.25)
            continue
        time.sleep(0.5)
    state = reconcile_daemon_state(DaemonState.load(path), path)
    return state if is_daemon_active(state) else None


def spawn_background() -> int:
    """Start recorder in a detached background process."""
    cfg = load_config()
    paths = cfg.ensure_directories()
    paths["logs"].mkdir(parents=True, exist_ok=True)
    spawn_log = paths["logs"] / "daemon-spawn.log"

    from app.install.portable import preferred_bgrec_executable

    exe = preferred_bgrec_executable()
    if getattr(sys, "frozen", False) or exe.name.lower() == "bgrec.exe":
        cmd = [str(exe), "start", "--foreground"]
    else:
        cmd = [sys.executable, "-m", "app.cli.main", "start", "--foreground"]

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    with spawn_log.open("a", encoding="utf-8") as log_fh:
        log_fh.write(f"\n--- spawn {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        log_fh.flush()
        proc = subprocess.Popen(
            cmd,
            creationflags=creationflags,
            close_fds=True,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
        )
    return proc.pid


def stop_daemon() -> StopResult:
    path = state_path()
    state = reconcile_daemon_state(DaemonState.load(path), path)

    pid = state.pid
    if not pid or not is_process_running(pid):
        return StopResult.NOT_RUNNING

    if not is_bgrec_process(pid, state.daemon_executable):
        state.running = False
        state.pid = None
        state.daemon_executable = None
        state.save(path)
        return StopResult.NOT_RUNNING

    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False, capture_output=True)
    else:
        os.kill(pid, signal.SIGTERM)

    for _ in range(20):
        if not is_process_running(pid):
            state.running = False
            state.pid = None
            state.daemon_executable = None
            state.save(path)
            return StopResult.STOPPED
        time.sleep(0.5)

    return StopResult.FAILED


def run_foreground(coordinator_factory) -> None:
    """Block in foreground running the coordinator."""
    from app.updater.service import run_startup_ota_if_needed

    cfg = load_config()
    paths = cfg.ensure_directories()
    configure_logging(
        paths["logs"],
        level=cfg.logging.level,
        max_bytes=cfg.logging.max_bytes,
        backup_count=cfg.logging.backup_count,
    )

    if run_startup_ota_if_needed():
        log.info("OTA applied on startup — exiting so the new version can run")
        sys.exit(0)

    path = state_path()
    state = reconcile_daemon_state(DaemonState.load(path), path)
    if state.pid and state.pid != os.getpid() and is_daemon_active(state):
        log.error("Another bgrec daemon is already running (pid={})", state.pid)
        sys.exit(1)

    coord = coordinator_factory()
    configure_logging(
        coord.paths["logs"],
        level=coord.config.logging.level,
        max_bytes=coord.config.logging.max_bytes,
        backup_count=coord.config.logging.backup_count,
    )

    def handle_signal(signum, frame):  # noqa: ARG001
        log.info("Received signal {}, shutting down", signum)
        coord.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, handle_signal)

    try:
        coord.start()
    except RuntimeError as exc:
        log.error("{}", exc)
        sys.exit(1)

    log.info("Running in foreground; press Ctrl+C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        coord.stop()
