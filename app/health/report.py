"""Merge daemon-reported issues with live checks for `bgrec status`."""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.config.settings import AppConfig
from app.recorder.converter import ffmpeg_available
from app.runtime_bootstrap import ssl_certificate_status
from app.service.state import DaemonState, HealthIssue
@dataclass(frozen=True)
class HealthReport:
    working_properly: bool
    issues: tuple[HealthIssue, ...]

    @property
    def healthy(self) -> bool:
        return self.working_properly


def _merge_issue(issues: dict[str, HealthIssue], code: str, message: str) -> None:
    issues[code] = HealthIssue(code=code, message=message.strip()[:500])


def assess_health(
    cfg: AppConfig,
    state: DaemonState,
    *,
    daemon_active: bool,
    auth_key: str,
    auth_msg: str,
) -> HealthReport:
    """Build the issue list shown in status (persisted + live checks)."""
    issues: dict[str, HealthIssue] = {i.code: i for i in state.issues}

    if not daemon_active:
        _merge_issue(issues, "daemon", "Recorder service is not running")

    chunk_s = cfg.recording.chunk_duration_seconds
    now = time.time()

    if daemon_active:
        if state.last_chunk_at:
            stale_limit = chunk_s * 2.5
            ago = now - state.last_chunk_at
            if ago > stale_limit:
                _merge_issue(
                    issues,
                    "recording",
                    f"No new audio chunk for {int(ago)}s (expected every {chunk_s}s)",
                )
        elif state.started_at and (now - state.started_at) > chunk_s * 2:
            _merge_issue(issues, "recording", "No chunks recorded since service started")

    if cfg.recording.output_format.lower() in ("mp3", "flac") and not ffmpeg_available():
        _merge_issue(
            issues,
            "ffmpeg",
            "ffmpeg not on PATH — chunks may stay WAV instead of "
            f"{cfg.recording.output_format.upper()}",
        )

    if cfg.upload.enabled:
        if auth_key == "authenticated":
            issues.pop("google_auth", None)
        else:
            _merge_issue(issues, "google_auth", auth_msg)

        tls_ok, tls_msg = ssl_certificate_status()
        if not tls_ok:
            _merge_issue(issues, "tls", tls_msg)

        if state.pending_uploads:
            pending_errors = [p.last_error for p in state.pending_uploads if p.last_error]
            if pending_errors and "upload" not in issues and "tls" not in issues:
                _merge_issue(issues, "upload", pending_errors[-1])
            elif len(state.pending_uploads) >= 1 and auth_key == "authenticated" and tls_ok:
                oldest = min(state.pending_uploads, key=lambda p: p.created_at)
                age = int(now - oldest.created_at)
                if age > max(120, cfg.upload.retry_delay_seconds * 3):
                    if "upload" not in issues:
                        _merge_issue(
                            issues,
                            "upload",
                            f"{len(state.pending_uploads)} file(s) waiting to upload "
                            f"(oldest {age}s)",
                        )

    ordered = sorted(issues.values(), key=lambda i: i.since)
    working = len(ordered) == 0 and daemon_active
    return HealthReport(working_properly=working, issues=tuple(ordered))


def format_issues_for_status(issues: tuple[HealthIssue, ...]) -> str:
    if not issues:
        return "none"
    return "; ".join(f"{i.code}: {i.message}" for i in issues)
