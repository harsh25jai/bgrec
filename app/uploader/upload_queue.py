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
from app.utils.file_busy import is_file_in_use
from app.utils.paths import safe_resolve

log = get_logger("upload_queue")

AUDIO_SUFFIXES = {".mp3", ".flac", ".wav"}


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
        self._process_lock = threading.Lock()

    def enqueue(self, source: Path) -> Path:
        """Queue a recording for upload. If encryption is on, keep .enc locally; upload plaintext to Drive."""
        with self._process_lock:
            return self._enqueue_unlocked(source)

    def _enqueue_unlocked(self, source: Path) -> Path:
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
        try:
            shutil.copy2(source, dest)
        except OSError as exc:
            if is_file_in_use(exc):
                raise RuntimeError(f"File is in use, will retry later: {source.name}") from exc
            raise
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

    def nudge(self) -> int:
        """Recover stray files and try uploads (after boot, wake, or reconnect)."""
        return self.process_pending(blocking=False)

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.process_pending()
            except Exception as exc:
                log.exception("Upload worker error: {}", exc)
                self._persist_issue("upload", str(exc))
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

        with self._process_lock:
            return self._process_pending_unlocked(blocking)

    def _persist_issue(self, code: str, message: str) -> None:
        if self.state.set_issue(code, message):
            self.state.save(self.state_path)

    def _clear_issues(self, *codes: str) -> None:
        changed = False
        for code in codes:
            if self.state.clear_issue(code):
                changed = True
        if changed:
            self.state.save(self.state_path)

    @staticmethod
    def _issue_code_for_upload_error(message: str) -> str:
        lower = message.lower()
        if "tls" in lower or "certificate" in lower or "ssl" in lower:
            return "tls"
        if ("not signed in" in lower or "login-google" in lower) and "discovery" not in lower:
            return "google_auth"
        if "discovery" in lower or "api metadata" in lower:
            return "upload"
        return "upload"

    def _process_pending_unlocked(self, blocking: bool = False) -> int:
        auth_key, auth_msg = self.drive.google_auth_status()
        if auth_key != "authenticated":
            log.debug("Google upload deferred: {}", auth_msg)
            self._persist_issue("google_auth", auth_msg)
            self._recover_orphans()
            return 0

        try:
            self.drive.authenticate(interactive=False)
            self._clear_issues("google_auth", "tls")
        except Exception as exc:
            msg = str(exc)
            log.warning("Drive auth failed: {} — files stay queued locally", exc)
            self._persist_issue(self._issue_code_for_upload_error(msg), msg)
            self._recover_orphans()
            return 0

        self._recover_orphans()
        pending = list(self.state.pending_uploads)

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
                    if err:
                        code = self._issue_code_for_upload_error(err)
                        self.state.set_issue(code, err)
                self.state.save(self.state_path)

        if uploaded:
            log.info("Uploaded {} file(s) to Drive", uploaded)
        if uploaded and not self.state.pending_uploads:
            self._clear_issues("upload", "tls", "google_auth")
        elif uploaded:
            self._clear_issues("google_auth")
        return uploaded

    def _recover_orphans(self) -> list[PendingUpload]:
        orphans: list[PendingUpload] = []
        scan_dirs = [self.pending_dir, self.paths["recordings"] / "encrypted"]
        seen = {p.local_path for p in self.state.pending_uploads}

        for directory in scan_dirs:
            if not directory.exists():
                continue
            for f in directory.iterdir():
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

        orphans.extend(self._recover_plain_recordings(seen))
        orphans.extend(self._recover_stale_plain_next_to_encrypted())

        if orphans:
            self.state.save(self.state_path)
            log.info("Recovered {} orphan pending upload(s)", len(orphans))
        return orphans

    def _recover_plain_recordings(self, seen: set[str]) -> list[PendingUpload]:
        """Pick up completed chunks left in recordings/ (e.g. offline, crash, sleep gap)."""
        recordings_dir = self.paths["recordings"]
        if not recordings_dir.exists():
            return []

        recovered: list[PendingUpload] = []
        enc_dir = recordings_dir / "encrypted"

        for f in sorted(recordings_dir.iterdir()):
            if not f.is_file() or f.suffix.lower() not in AUDIO_SUFFIXES:
                continue
            if f.suffix.lower() == ".wav":
                mp3 = f.with_suffix(".mp3")
                if mp3.exists():
                    continue
            key = str(f.resolve())
            if key in seen:
                continue
            if enc_dir.exists() and (enc_dir / f"{f.name}.enc").exists():
                continue
            if (self.pending_dir / f.name).exists():
                continue
            try:
                queued = self._enqueue_unlocked(f)
                key = str(queued.resolve())
                if key not in seen:
                    seen.add(key)
                    for pu in self.state.pending_uploads:
                        if pu.local_path == key:
                            recovered.append(pu)
                            break
                log.info("Re-queued recording for upload: {}", f.name)
            except Exception as exc:
                if is_file_in_use(exc):
                    log.debug("Skipping re-queue (file in use): {}", f.name)
                    continue
                log.warning("Could not re-queue {}: {}", f.name, exc)
        return recovered

    def _recover_stale_plain_next_to_encrypted(self) -> list[PendingUpload]:
        """Remove duplicate plaintext when .enc already exists."""
        recordings_dir = self.paths["recordings"]
        enc_dir = recordings_dir / "encrypted"
        if not enc_dir.exists():
            return []
        for f in recordings_dir.iterdir():
            if not f.is_file() or f.suffix.lower() not in AUDIO_SUFFIXES:
                continue
            enc_path = enc_dir / f"{f.name}.enc"
            if enc_path.exists():
                try:
                    f.unlink(missing_ok=True)
                except OSError as exc:
                    if is_file_in_use(exc):
                        log.debug("Plaintext in use, keeping until next pass: {}", f.name)
                        continue
                    raise
                log.debug("Removed stale plaintext (encrypted copy kept): {}", f.name)
        return []
