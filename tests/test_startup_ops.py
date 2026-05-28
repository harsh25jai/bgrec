"""Fresh start helpers (stop daemon, clear logs)."""

from __future__ import annotations

from pathlib import Path

from app.logging.setup import clear_log_directory
from app.service.state import DaemonState, PendingUpload
from app.service.startup_ops import pending_upload_summary


def test_clear_log_directory_removes_log_files(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "app.log").write_text("old", encoding="utf-8")
    (log_dir / "daemon-spawn.log").write_text("spawn", encoding="utf-8")
    (log_dir / "app.log.2026-05-27.zip").write_text("zip", encoding="utf-8")
    (log_dir / "keep.txt").write_text("x", encoding="utf-8")

    removed = clear_log_directory(log_dir)
    assert removed == 3
    assert not (log_dir / "app.log").exists()
    assert (log_dir / "keep.txt").exists()


def test_pending_upload_summary() -> None:
    state = DaemonState(pending_uploads=[])
    assert pending_upload_summary(state) == (0, False)
    state.pending_uploads.append(PendingUpload(local_path="/a", remote_name="a.mp3"))
    count, has = pending_upload_summary(state)
    assert count == 1
    assert has is True
