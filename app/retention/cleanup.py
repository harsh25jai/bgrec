"""Local file retention and cache cleanup."""

from __future__ import annotations

import time
from pathlib import Path

from app.config.settings import AppConfig
from app.logging.setup import get_logger

log = get_logger("retention")


class RetentionManager:
    def __init__(self, config: AppConfig, paths: dict[str, Path]) -> None:
        self.config = config
        self.paths = paths

    def run_cleanup(self) -> int:
        removed = 0
        days = self.config.retention.local_retention_days
        if days <= 0:
            return 0
        cutoff = time.time() - days * 86400
        dirs = [
            self.paths["recordings"],
            self.paths["recordings"] / "encrypted",
            self.paths["pending_uploads"],
            self.paths["cache"] / "upload_temp",
            self.paths["cache"],
        ]
        for directory in dirs:
            if not directory.exists():
                continue
            for f in directory.rglob("*"):
                if f.is_file() and f.stat().st_mtime < cutoff:
                    try:
                        f.unlink()
                        removed += 1
                    except OSError as exc:
                        log.warning("Could not delete {}: {}", f, exc)
        if removed:
            log.info("Retention cleanup removed {} file(s)", removed)
        return removed

    def delete_local_cache(self) -> int:
        removed = 0
        for directory in (self.paths["cache"], self.paths["pending_uploads"]):
            if not directory.exists():
                continue
            for f in directory.rglob("*"):
                if f.is_file():
                    f.unlink(missing_ok=True)
                    removed += 1
        log.info("Deleted {} cached file(s)", removed)
        return removed
