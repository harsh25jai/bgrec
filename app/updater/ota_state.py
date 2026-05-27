"""OTA apply locks and failure backoff (avoids download loops on every start)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from app.config.settings import default_data_dirs
from app.updater.manifest import compare_versions
from app.version import normalize_version

FAILURE_FILE = "last-failure.json"
APPLY_LOCK = ".apply-in-progress"
# After a failed apply, skip auto-apply for this long unless user runs `bgrec update --yes`
BACKOFF_SECONDS = 6 * 3600


def updates_dir() -> Path:
    path = default_data_dirs()["root"] / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def apply_lock_path() -> Path:
    return updates_dir() / APPLY_LOCK


def failure_path() -> Path:
    return updates_dir() / FAILURE_FILE


def is_apply_in_progress() -> bool:
    lock = apply_lock_path()
    if not lock.exists():
        return False
    try:
        age = time.time() - lock.stat().st_mtime
        if age > 3600:
            lock.unlink(missing_ok=True)
            return False
    except OSError:
        return False
    return True


def acquire_apply_lock() -> bool:
    if is_apply_in_progress():
        return False
    try:
        apply_lock_path().write_text(str(time.time()), encoding="utf-8")
        return True
    except OSError:
        return False


def release_apply_lock() -> None:
    apply_lock_path().unlink(missing_ok=True)


def read_apply_failure() -> dict:
    path = failure_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def record_apply_failure(version: str, error: str) -> None:
    payload = {
        "version": version,
        "error": error[:500],
        "at": time.time(),
    }
    try:
        failure_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


def clear_apply_failure() -> None:
    failure_path().unlink(missing_ok=True)


def auto_apply_backoff_active(*, force: bool = False) -> bool:
    if force:
        return False
    data = read_apply_failure()
    if not data:
        return False
    at = float(data.get("at") or 0)
    if time.time() - at > BACKOFF_SECONDS:
        return False
    return True


def backoff_message() -> str | None:
    data = read_apply_failure()
    if not data or not auto_apply_backoff_active():
        return None
    ver = data.get("version", "?")
    err = data.get("error", "unknown")
    remaining_h = max(1, int((BACKOFF_SECONDS - (time.time() - float(data.get("at") or 0))) / 3600))
    return (
        f"OTA auto-apply paused after failed install of {ver}: {err}. "
        f"Retry in ~{remaining_h}h or run: bgrec update --yes"
    )


def already_at_release(current: str, remote: str, last_applied: str | None) -> bool:
    """True when installed version is already at or past the release."""
    del last_applied
    try:
        return compare_versions(normalize_version(current), normalize_version(remote)) >= 0
    except ValueError:
        return False
