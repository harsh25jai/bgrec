"""Periodic health check thread."""

from __future__ import annotations

import threading
from typing import Callable

from app.logging.setup import get_logger

log = get_logger("watchdog")


class Watchdog:
    def __init__(self, check_fn: Callable[[], bool], interval_seconds: float = 60.0) -> None:
        self.check_fn = check_fn
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval_seconds + 5)

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.check_fn()
            except Exception as exc:
                log.exception("Watchdog check failed: {}", exc)
