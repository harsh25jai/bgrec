"""Background periodic OTA checks while the daemon is running."""

from __future__ import annotations

import threading

from app.config.settings import AppConfig
from app.logging.setup import get_logger
from app.updater.service import run_periodic_update_check

log = get_logger("updater.scheduler")


class UpdateScheduler:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _interval_seconds(self) -> float:
        hours = max(1, self.config.update.check_interval_hours)
        return hours * 3600.0

    def start(self) -> None:
        if not self.config.update.enabled or not self.config.update.auto_apply:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="ota-scheduler", daemon=True)
        self._thread.start()
        log.debug("OTA scheduler started (every {}h)", self.config.update.check_interval_hours)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)

    def _loop(self) -> None:
        while not self._stop.wait(self._interval_seconds()):
            try:
                run_periodic_update_check()
            except Exception as exc:
                log.exception("Periodic OTA check failed: {}", exc)
