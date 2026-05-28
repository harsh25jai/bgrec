"""Daemon/CLI state.json issue sync (blocker A)."""

from __future__ import annotations

import json
from pathlib import Path

from app.service.state import DaemonState, HealthIssue
from app.service.state_sync import sync_issues_from_disk


def test_save_runtime_preserves_issues_on_disk(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "pid": 1,
                "running": True,
                "issues": [{"code": "upload", "message": "err", "since": 1.0}],
                "issues_revision": 3,
                "pending_uploads": [],
            }
        ),
        encoding="utf-8",
    )

    daemon = DaemonState.load(path)
    daemon.issues.append(HealthIssue(code="google_auth", message="stale in memory"))
    daemon.issues_revision = 1
    daemon.last_heartbeat_at = 99.0
    daemon.save_runtime(path)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["issues"]) == 1
    assert data["issues"][0]["code"] == "upload"
    assert data["issues_revision"] == 3
    assert data["last_heartbeat_at"] == 99.0


def test_cli_clear_visible_to_daemon_memory(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    daemon = DaemonState(
        pid=100,
        running=True,
        issues=[HealthIssue(code="google_auth", message="Not signed in")],
        issues_revision=1,
    )
    daemon.save(path)

    disk = DaemonState.load(path)
    disk.clear_issues("google_auth", "upload", "tls")
    disk.save(path)

    sync_issues_from_disk(daemon, path)
    assert daemon.issues == []
    assert daemon.issues_revision == disk.issues_revision


def test_clear_persisted_bumps_revision(tmp_path: Path, monkeypatch) -> None:
    from app.health import state_issues

    path = tmp_path / "state.json"
    state = DaemonState(
        issues=[HealthIssue(code="google_auth", message="x")],
        issues_revision=2,
    )
    state.save(path)
    monkeypatch.setattr(state_issues, "state_path", lambda: path)

    assert state_issues.clear_persisted_health_issues("google_auth")
    loaded = DaemonState.load(path)
    assert loaded.issues == []
    assert loaded.issues_revision == 3
