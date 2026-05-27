"""Coordinates recording, uploads, retention, and watchdog."""

from __future__ import annotations

import os
import time
from pathlib import Path

from app.config.settings import AppConfig, load_config
from app.platform_check import require_windows
from app.crypto.encryption import EncryptionManager
from app.logging.setup import configure_logging, get_logger
from app.recorder.audio_recorder import ChunkRecorder
from app.retention.cleanup import RetentionManager
from app.service.state import DaemonState
from app.service.watchdog import Watchdog
from app.uploader.drive_client import DriveClient
from app.uploader.upload_queue import UploadQueue

log = get_logger("coordinator")


class ServiceCoordinator:
    def __init__(self, config: AppConfig | None = None) -> None:
        require_windows()
        self.config = config or load_config()
        self.paths = self.config.ensure_directories()
        configure_logging(
            self.paths["logs"],
            level=self.config.logging.level,
            max_bytes=self.config.logging.max_bytes,
            backup_count=self.config.logging.backup_count,
        )
        self.state_path = self.paths["root"] / "state.json"
        self.state = DaemonState.load(self.state_path)
        self.encryption = EncryptionManager(
            self.paths["root"] / "encryption.key",
            enabled=self.config.encryption.enabled,
        )
        self.drive = DriveClient(
            self.paths["credentials"],
            credentials_file=self.config.google.credentials_file,
            token_file=self.config.google.token_file,
            app_folder_name=self.config.google.app_folder_name,
        )
        self.upload_queue = UploadQueue(
            self.config,
            self.paths,
            self.state,
            self.state_path,
            self.encryption,
            self.drive,
        )
        self.recorder = ChunkRecorder(
            self.config.recording,
            self.paths["recordings"],
            on_chunk=self._on_chunk,
        )
        self.retention = RetentionManager(self.config, self.paths)
        self.watchdog = Watchdog(self._health_check, interval_seconds=60)

    def _on_chunk(self, path: Path) -> None:
        self.state.last_chunk_at = time.time()
        self.state.chunks_recorded += 1
        self.state.save(self.state_path)
        if self.config.upload.enabled:
            self.upload_queue.enqueue(path)
        self.retention.run_cleanup()

    def _health_check(self) -> bool:
        if not self.recorder.is_running:
            log.warning("Watchdog: recorder not running — restarting")
            self.recorder.start()
            return False
        return True

    def start(self) -> None:
        self.state.pid = os.getpid()
        self.state.running = True
        self.state.started_at = time.time()
        self.state.save(self.state_path)

        self.recorder.start()
        self.upload_queue.start_worker()
        self.watchdog.start()
        log.info("Service coordinator started (pid={})", self.state.pid)

    def stop(self) -> None:
        self.watchdog.stop()
        self.recorder.stop()
        self.upload_queue.stop_worker()
        self.state.running = False
        self.state.pid = None
        self.state.save(self.state_path)
        log.info("Service coordinator stopped")

    def status_dict(self) -> dict:
        return {
            "running": self.state.running,
            "pid": self.state.pid,
            "started_at": self.state.started_at,
            "last_chunk_at": self.state.last_chunk_at,
            "chunks_recorded": self.state.chunks_recorded,
            "pending_uploads": len(self.state.pending_uploads),
            "recorder_active": self.recorder.is_running,
            "paths": {k: str(v) for k, v in self.paths.items()},
        }
