"""Health reporting and daemon issue persistence."""

from __future__ import annotations

import time

from app.config.settings import AppConfig
from app.health.report import assess_health, format_issues_for_status
from app.service.state import DaemonState, HealthIssue


def _minimal_config(**kwargs) -> AppConfig:
    cfg = AppConfig()
    cfg.upload.enabled = kwargs.get("upload_enabled", True)
    cfg.recording.chunk_duration_seconds = 300
    cfg.recording.output_format = kwargs.get("output_format", "mp3")
    return cfg


def test_daemon_state_set_and_clear_issue() -> None:
    state = DaemonState()
    assert state.set_issue("upload", "TLS failed")
    assert len(state.issues) == 1
    assert not state.set_issue("upload", "TLS failed")
    assert state.set_issue("upload", "Network down")
    assert state.issues[0].message == "Network down"
    assert state.clear_issue("upload")
    assert state.issues == []


def test_assess_health_daemon_stopped() -> None:
    cfg = _minimal_config(upload_enabled=False)
    state = DaemonState()
    report = assess_health(cfg, state, daemon_active=False, auth_key="skip", auth_msg="upload off")
    assert not report.working_properly
    codes = {i.code for i in report.issues}
    assert "daemon" in codes


def test_assess_health_merges_persisted_upload_issue() -> None:
    cfg = _minimal_config()
    state = DaemonState(
        running=True,
        pid=99999,
        started_at=time.time() - 10,
        last_chunk_at=time.time() - 30,
        issues=[HealthIssue(code="tls", message="invalid cacert.pem")],
    )
    report = assess_health(
        cfg,
        state,
        daemon_active=True,
        auth_key="authenticated",
        auth_msg="ok",
    )
    assert not report.working_properly
    assert any(i.code == "tls" for i in report.issues)


def test_format_issues_for_status() -> None:
    issues = (HealthIssue(code="tls", message="bad cert"),)
    text = format_issues_for_status(issues)
    assert "tls:" in text
    assert format_issues_for_status(()) == "none"
