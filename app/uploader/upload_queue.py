"""Background upload queue with retries and persistence."""

from __future__ import annotations

import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.config.settings import AppConfig
from app.crypto.encryption import EncryptionManager
from app.logging.setup import get_logger
from app.service.state import DaemonState, PendingUpload
from app.uploader.drive_client import DriveClient
from app.utils.paths import safe_resolve

log = get_logger("upload_queue")


def plain_remote_name(remote_name: str, local_path: Path) -> str:
    """Drive filename: plaintext audio (never .enc)."""
    if remote_name.endswith(".enc"):
        return remote_name[: -len(".enc")]
    if local_path.suffix == ".enc" and local_path.name.endswith(".enc"):
        return local_path.name[: -len(".enc")]
    return remote_name


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
        """Queue a recording for upload. If encryption is on, keep .enc locally; upload plaintext to Drive."""
        safe_resolve(source, self.paths["recordings"])
        self.pending_dir.mkdir(parents=True, exist_ok=True)

        if self.config.encryption.enabled:
            enc_dir = self.paths["recordings"] / "encrypted"
            enc_dir.mkdir(parents=True, exist_ok=True)
            enc_path = enc_dir / f"{source.name}.enc"
            self.encryption.encrypt_file(source, enc_path)
            source.unlink(missing_ok=True)
            remote_name = source.name
            self.state.add_pending(enc_path, remote_name)
            self.state.save(self.state_path)
            log.info("Encrypted locally: {} (Drive upload will be {})", enc_path.name, remote_name)
            return enc_path

        dest = self.pending_dir / source.name
        shutil.copy2(source, dest)
        if self.config.retention.delete_after_upload:
            source.unlink(missing_ok=True)
        self.state.add_pending(dest, dest.name)
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

    def _prepare_upload_file(self, local_path: Path, remote_name: str) -> tuple[Path, str, Path | None]:
        """
        Return (path_to_upload, drive_filename, temp_plain_path).
        temp_plain_path is set when a decrypted temp file must be deleted after upload.
        """
        drive_name = plain_remote_name(remote_name, local_path)
        if not self.config.encryption.enabled or local_path.suffix != ".enc":
            return local_path, drive_name, None

        upload_temp = self.paths["cache"] / "upload_temp"
        upload_temp.mkdir(parents=True, exist_ok=True)
        temp_plain = upload_temp / drive_name
        self.encryption.decrypt_file(local_path, temp_plain)
        log.debug("Decrypted for upload: {} -> {}", local_path.name, drive_name)
        return temp_plain, drive_name, temp_plain

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
            log.warning("Drive auth failed: {} — files stay in local queue", exc)
            return 0

        pending = list(self.state.pending_uploads)
        if not pending:
            pending = self._recover_orphans()

        if not pending:
            return 0

        uploaded = 0
        workers = max(1, self.config.upload.upload_workers)

        def upload_one(item: PendingUpload):
            path = Path(item.local_path)
            if not path.exists():
                return item, True, None
            temp_plain: Path | None = None
            for attempt in range(1, self.config.upload.retry_max_attempts + 1):
                try:
                    upload_path, drive_name, temp_plain = self._prepare_upload_file(path, item.remote_name)
                    self.drive.upload_file(upload_path, drive_name)
                    if temp_plain and temp_plain.exists():
                        temp_plain.unlink(missing_ok=True)
                    if self.config.retention.delete_after_upload and path.exists():
                        path.unlink(missing_ok=True)
                    return item, True, None
                except Exception as exc:
                    if temp_plain and temp_plain.exists():
                        temp_plain.unlink(missing_ok=True)
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

    def _recover_orphans(self) -> list[PendingUpload]:
        orphans: list[PendingUpload] = []
        scan_dirs = [self.pending_dir, self.paths["recordings"] / "encrypted"]
        seen = {p.local_path for p in self.state.pending_uploads}

        for directory in scan_dirs:
            if not directory.exists():
                continue
            for f in directory.glob("*"):
                if not f.is_file() or f.name.endswith(".lock"):
                    continue
                key = str(f.resolve())
                if key in seen:
                    continue
                remote = plain_remote_name(f.name, f)
                pu = PendingUpload(local_path=key, remote_name=remote)
                self.state.pending_uploads.append(pu)
                orphans.append(pu)
                seen.add(key)

        if orphans:
            self.state.save(self.state_path)
            log.info("Recovered {} orphan pending uploads", len(orphans))
        return orphans
