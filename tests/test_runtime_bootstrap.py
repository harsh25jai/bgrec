"""Runtime bootstrap for frozen Windows (TLS, Drive discovery)."""

from __future__ import annotations

import sys
from pathlib import Path

from app.runtime_bootstrap import (
    configure_drive_discovery_cache,
    drive_discovery_status,
)


def test_persistent_discovery_used_without_bundle(tmp_path, monkeypatch) -> None:
    persistent = tmp_path / "Local" / "bgrec" / "discovery_cache" / "documents"
    persistent.mkdir(parents=True)
    (persistent / "drive.v3.json").write_text(
        '{"name": "drive", "version": "v3", "resources": {}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    from app.runtime_bootstrap import configure_drive_discovery_cache, drive_discovery_status

    assert configure_drive_discovery_cache() == persistent
    ok, _ = drive_discovery_status()
    assert ok


def test_frozen_discovery_copied_to_localappdata(tmp_path, monkeypatch) -> None:
    meipass = tmp_path / "_MEI123"
    bundled = meipass / "googleapiclient" / "discovery_cache" / "documents"
    bundled.mkdir(parents=True)
    (bundled / "drive.v3.json").write_text(
        '{"name": "drive", "version": "v3", "resources": {}}',
        encoding="utf-8",
    )

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)

    doc_dir = configure_drive_discovery_cache()
    assert doc_dir is not None
    persistent = tmp_path / "Local" / "bgrec" / "discovery_cache" / "documents" / "drive.v3.json"
    assert persistent.is_file()

    ok, _ = drive_discovery_status()
    assert ok
