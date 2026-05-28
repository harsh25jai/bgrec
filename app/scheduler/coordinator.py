"""Coordinates recording, uploads, retention, and watchdog."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from app.config.settings import AppConfig, load_config
from app.platform_check import require_windows
from app.runtime_bootstrap import bootstrap_runtime
from app.crypto.encryption import EncryptionManager
from app.logging.setup import configure_logging, get_logger
from app.recorder.audio_recorder import ChunkRecorder
from app.retention.cleanup import RetentionManager
from app.service.singleton import DaemonInstanceLock
from app.service.sleep_guard import SleepGuard
from app.service.state import DaemonState
from app.service.state_sync import sync_issues_from_disk
from app.service.watchdog import Watchdog
from app.uploader.drive_client import DriveClient
from app.uploader.upload_queue import UploadQueue

log = get_logger("coordinator")


class ServiceCoordinator:
    def __init__(self, config: AppConfig | None = None) -> None:
        require_windows()
        bootstrap_runtime()
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
        watchdog_interval = 15 if self.config.recording.prevent_sleep_during_recording else 60
        self.watchdog = Watchdog(self._health_check, interval_seconds=watchdog_interval)
        self.sleep_guard = SleepGuard(
            enabled=self.config.recording.prevent_sleep_during_recording,
            on_resume=self._on_system_resume,
        )
        self._instance_lock = DaemonInstanceLock()
        self._update_scheduler = None

    def _on_chunk(self, path: Path) -> None:
        sync_issues_from_disk(self.state, self.state_path)
        self.state.last_chunk_at = time.time()
        self.state.chunks_recorded += 1
        self.state.clear_issue("recording")
        self.state.save_runtime(self.state_path)
        if self.config.upload.enabled:
            self.upload_queue.enqueue(path)
        pending_paths = {p.local_path for p in self.state.pending_uploads}
        self.retention.run_cleanup(pending_paths)

    def _recycle_recorder(self, reason: str) -> None:
        log.warning("Recycling audio stream: {}", reason)
        self.recorder.stop()
        self.recorder.start()

    def _on_system_resume(self) -> None:
        self._recycle_recorder("system resume from sleep/hibernate")
        if self.config.upload.enabled:
            log.info("System resumed — retrying pending uploads")
            self.upload_queue.nudge()

    def _touch_heartbeat(self) -> None:
        sync_issues_from_disk(self.state, self.state_path)
        self.state.last_heartbeat_at = time.time()
        self.state.save_runtime(self.state_path)
        sync_issues_from_disk(self.state, self.state_path)

    def _health_check(self) -> bool:
        self._touch_heartbeat()
        if not self.recorder.is_running:
            log.warning("Watchdog: recorder not running — restarting")
            self.recorder.start()
            return False
        if self.state.last_chunk_at:
            stale_limit = self.config.recording.chunk_duration_seconds * 2.5
            ago = time.time() - self.state.last_chunk_at
            if ago > stale_limit:
                msg = f"No new audio chunk for {int(ago)}s"
                sync_issues_from_disk(self.state, self.state_path)
                if self.state.set_issue("recording", msg):
                    self.state.save(self.state_path)
                self._recycle_recorder("no recent audio chunks (possible sleep or mic loss)")
                return False
        elif self.state.started_at:
            grace = self.config.recording.chunk_duration_seconds * 2
            if time.time() - self.state.started_at > grace:
                msg = "No chunks recorded since service started"
                sync_issues_from_disk(self.state, self.state_path)
                if self.state.set_issue("recording", msg):
                    self.state.save(self.state_path)
        if self.config.upload.enabled and self.state.pending_uploads:
            self.upload_queue.nudge()
        return True

    def start(self) -> None:
        if not self._instance_lock.acquire():
            raise RuntimeError(
                "Another bgrec recording daemon is already running. "
                "Run: bgrec stop   then: bgrec start --background"
            )

        from app.install.portable import preferred_bgrec_executable

        self.state.pid = os.getpid()
        self.state.daemon_executable = str(preferred_bgrec_executable())
        self.state.running = True
        self.state.started_at = time.time()
        self.state.clear_issue("daemon")
        self._touch_heartbeat()
        self.state.save(self.state_path)

        self.sleep_guard.acquire()
        self.recorder.start()
        from app.updater.scheduler import UpdateScheduler

        self._update_scheduler = UpdateScheduler(self.config)
        self._update_scheduler.start()
        self.upload_queue.start_worker()
        if self.config.upload.enabled:
            recovered = self.upload_queue.nudge()
            if recovered or self.state.pending_uploads:
                log.info(
                    "Upload queue on start: {} pending file(s)",
                    len(self.state.pending_uploads),
                )
        self.watchdog.start()
        log.info("Service coordinator started (pid={})", self.state.pid)

    def stop(self) -> None:
        if self._update_scheduler:
            self._update_scheduler.stop()
        self.watchdog.stop()
        self.recorder.stop()
        self.upload_queue.stop_worker()
        self.sleep_guard.release()
        self._instance_lock.release()
        self.state.running = False
        self.state.pid = None
        self.state.daemon_executable = None
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
