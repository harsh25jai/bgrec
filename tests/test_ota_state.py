"""OTA backoff and version-at-release helpers."""

from __future__ import annotations

from app.updater.ota_state import already_at_release, auto_apply_backoff_active, record_apply_failure


def test_already_at_release() -> None:
    assert already_at_release("0.0.2", "0.0.2", "0.0.2")
    assert already_at_release("0.0.3", "0.0.2", None)
    assert not already_at_release("0.0.1", "0.0.2", None)


def test_apply_backoff_after_failure(monkeypatch, tmp_path) -> None:
    import app.updater.ota_state as ota_state

    monkeypatch.setattr(ota_state, "default_data_dirs", lambda: {"root": tmp_path})
    record_apply_failure("0.0.2", "disk full")
    assert auto_apply_backoff_active()
    assert not auto_apply_backoff_active(force=True)
