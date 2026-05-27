"""Background upload queue with retries and persistence."""

from __future__ import annotations

import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.config.settings import AppConfig
from app.utils.paths import safe_resolve
from app.crypto.encryption import EncryptionManager
from app.logging.setup import get_logger
from app.service.state import DaemonState
from app.uploader.drive_client import DriveClient

log = get_logger("upload_queue")


class UploadQueue:
    def __init__(
        self,
        config: AppConfig,
        paths: dict[str, Path],
        state: DaemonState,
        state_path: Path,
        encryption: EncryptionManager,
        drive: DriveClient,
    ) -> None:
        self.config = config
        self.paths = paths
        self.state = state
        self.state_path = state_path
        self.encryption = encryption
        self.drive = drive
        self.pending_dir = paths["pending_uploads"]
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def enqueue(self, source: Path) -> Path:
        """Copy/encrypt file into pending directory and track in state."""
        safe_resolve(source, self.paths["recordings"])
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        dest = self.pending_dir / source.name

        if self.config.encryption.enabled:
            enc_path = self.encryption.encrypt_file(source, dest.with_suffix(dest.suffix + ".enc"))
            dest = enc_path
            if source.exists():
                source.unlink()
        else:
            shutil.copy2(source, dest)
            if self.config.retention.delete_after_upload:
                source.unlink(missing_ok=True)

        remote_name = dest.name
        self.state.add_pending(dest, remote_name)
        self.state.save(self.state_path)
        log.info("Queued for upload: {}", dest.name)
        return dest

    def start_worker(self) -> None:
        if not self.config.upload.enabled:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker_loop, name="upload-worker", daemon=True)
        self._thread.start()

    def stop_worker(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=30)

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.process_pending()
            except Exception as exc:
                log.exception("Upload worker error: {}", exc)
            self._stop.wait(self.config.upload.retry_delay_seconds)

    def process_pending(self, blocking: bool = False) -> int:
        if not self.config.upload.enabled:
            return 0
        auth_key, auth_msg = self.drive.google_auth_status()
        if auth_key != "authenticated":
            log.warning("Google upload skipped: {}", auth_msg)
            return 0

        try:
            self.drive.authenticate(interactive=False)
        except Exception as exc:
            log.warning("Drive auth failed: {} — files stay in pending queue", exc)
            return 0

        pending = list(self.state.pending_uploads)
        if not pending:
            # Scan pending dir for orphan files after crash
            pending = self._recover_orphans()

        if not pending:
            return 0

        uploaded = 0
        workers = max(1, self.config.upload.upload_workers)

        def upload_one(item):
            path = Path(item.local_path)
            if not path.exists():
                return item, True, None
            for attempt in range(1, self.config.upload.retry_max_attempts + 1):
                try:
                    self.drive.upload_file(path, item.remote_name)
                    path.unlink(missing_ok=True)
                    return item, True, None
                except Exception as exc:
                    item.attempts = attempt
                    item.last_error = str(exc)
                    if attempt < self.config.upload.retry_max_attempts:
                        time.sleep(self.config.upload.retry_delay_seconds)
            return item, False, item.last_error

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(upload_one, p): p for p in pending}
            for fut in as_completed(futures):
                item, ok, err = fut.result()
                if ok:
                    self.state.remove_pending(Path(item.local_path))
                    uploaded += 1
                else:
                    log.error("Failed upload after retries: {} — {}", item.remote_name, err)
                self.state.save(self.state_path)

        return uploaded

    def _recover_orphans(self) -> list:
        from app.service.state import PendingUpload

        orphans = []
        for f in self.pending_dir.glob("*"):
            if f.is_file() and not f.name.endswith(".lock"):
                pu = PendingUpload(local_path=str(f), remote_name=f.name)
                self.state.pending_uploads.append(pu)
                orphans.append(pu)
        if orphans:
            self.state.save(self.state_path)
            log.info("Recovered {} orphan pending uploads", len(orphans))
        return orphans
