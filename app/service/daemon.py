"""Background daemon process management."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from app.config.settings import default_config_path, load_config
from app.logging.setup import configure_logging, get_logger
from app.service.state import DaemonState

log = get_logger("daemon")


def state_path() -> Path:
    cfg = load_config()
    return cfg.ensure_directories()["root"] / "state.json"


def is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def spawn_background() -> int:
    """Start recorder in a detached background process."""
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "start", "--foreground"]
    else:
        cmd = [sys.executable, "-m", "app.cli.main", "start", "--foreground"]

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(
        cmd,
        creationflags=creationflags,
        close_fds=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.pid


def stop_daemon() -> bool:
    state = DaemonState.load(state_path())
    if not state.pid or not state.running:
        return False
    pid = state.pid
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False, capture_output=True)
    else:
        os.kill(pid, signal.SIGTERM)
    for _ in range(20):
        if not is_process_running(pid):
            state.running = False
            state.pid = None
            state.save(state_path())
            return True
        time.sleep(0.5)
    return False


def run_foreground(coordinator_factory) -> None:
    """Block in foreground running the coordinator."""
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

    coord.start()
    log.info("Running in foreground; press Ctrl+C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        coord.stop()
