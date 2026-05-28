"""Sync health issues between CLI and daemon via state.json."""

from __future__ import annotations

from pathlib import Path

from app.service.state import DaemonState


def sync_issues_from_disk(state: DaemonState, path: Path) -> bool:
    """
    Pull issues + issues_revision from disk into the in-memory state.

    Used before the daemon mutates or persists issues so CLI clears (login-google)
    are not overwritten by stale in-memory data.
    """
    if not path.exists():
        return False
    disk = DaemonState.load(path)
    if disk.issues_revision == state.issues_revision and disk.issues == state.issues:
        return False
    state.issues = list(disk.issues)
    state.issues_revision = disk.issues_revision
    return True
