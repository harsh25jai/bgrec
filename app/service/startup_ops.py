"""Fresh service start: stop daemon, clear logs, reconcile state."""

from __future__ import annotations

import time
from pathlib import Path

from app.logging.setup import clear_log_directory
from app.service.daemon import (
    StopResult,
    is_bgrec_process,
    is_daemon_active,
    is_process_running,
    reconcile_daemon_state,
    state_path,
    stop_daemon,
)
from app.service.state import DaemonState


def stop_existing_daemon_for_restart(*, quiet: bool = False) -> StopResult:
    """
    Stop a running or orphan bgrec daemon so a new instance can start cleanly.

    Returns the stop outcome (NOT_RUNNING if nothing was running).
    """
    path = state_path()
    state = reconcile_daemon_state(DaemonState.load(path), path)

    if is_daemon_active(state):
        result = stop_daemon()
        if result == StopResult.STOPPED and not quiet:
            time.sleep(1.0)
        return result

    if (
        state.pid
        and is_process_running(state.pid)
        and is_bgrec_process(state.pid, state.daemon_executable)
    ):
        result = stop_daemon()
        if result == StopResult.STOPPED and not quiet:
            time.sleep(1.0)
        return result

    return StopResult.NOT_RUNNING


def prepare_fresh_service_start(log_dir: Path) -> tuple[StopResult, int]:
    """
    Stop any existing daemon and remove stale log files under log_dir.

    Returns (stop_result, number of log files removed).
    """
    stop_result = stop_existing_daemon_for_restart(quiet=True)
    if stop_result == StopResult.STOPPED:
        time.sleep(1.0)
    removed = clear_log_directory(log_dir)
    return stop_result, removed


def pending_upload_summary(state: DaemonState | None) -> tuple[int, bool]:
    """Return (pending_count, has_entries)."""
    if not state:
        return 0, False
    return len(state.pending_uploads), bool(state.pending_uploads)
