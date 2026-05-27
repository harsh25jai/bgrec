"""Local file retention and cache cleanup."""

from __future__ import annotations

import time
from pathlib import Path

from app.config.settings import AppConfig
from app.logging.setup import get_logger

log = get_logger("retention")

AUDIO_SUFFIXES = {".mp3", ".flac", ".wav"}


class RetentionManager:
    def __init__(self, config: AppConfig, paths: dict[str, Path]) -> None:
        self.config = config
        self.paths = paths

    def run_cleanup(self, pending_local_paths: set[str] | None = None) -> int:
        """
        Age-based cleanup for stray plaintext in recordings/ only.

        Does NOT delete pending queue, encrypted vault, or paths still in upload state —
        those are removed by delete_after_upload after a successful Drive upload.
        """
        removed = 0
        days = self.config.retention.local_retention_days
        if days <= 0:
            return 0

        pending_local_paths = pending_local_paths or set()
        cutoff = time.time() - days * 86400
        recordings_dir = self.paths["recordings"]

        if recordings_dir.exists():
            for f in recordings_dir.iterdir():
                if not f.is_file() or f.suffix.lower() not in AUDIO_SUFFIXES:
                    continue
                key = str(f.resolve())
                if key in pending_local_paths:
                    continue
                if f.stat().st_mtime >= cutoff:
                    continue
                try:
                    f.unlink()
                    removed += 1
                except OSError as exc:
                    log.warning("Could not delete {}: {}", f, exc)

        upload_temp = self.paths["cache"] / "upload_temp"
        if upload_temp.exists():
            for f in upload_temp.iterdir():
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
