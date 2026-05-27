"""Persisted daemon health issues (state.json)."""

from __future__ import annotations

from app.service.daemon import state_path
from app.service.state import DaemonState

ISSUES_CLEARED_AFTER_GOOGLE_LOGIN = ("google_auth", "upload", "tls")


def clear_persisted_health_issues(*codes: str) -> bool:
    """Remove issue codes from state.json; returns True if anything changed."""
    path = state_path()
    if not path.exists():
        return False
    state = DaemonState.load(path)
    changed = any(state.clear_issue(code) for code in codes)
    if changed:
        state.save(path)
    return changed
