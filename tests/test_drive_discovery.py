"""Google Drive static discovery (PyInstaller bundle prerequisite)."""

from __future__ import annotations

from pathlib import Path

from googleapiclient.discovery_cache import get_static_doc


def test_drive_v3_static_discovery_available() -> None:
    doc = get_static_doc("drive", "v3")
    assert doc
    assert "drive" in doc.lower()


def test_pyinstaller_includes_discovery_documents_path() -> None:
    from scripts.pyinstaller_build import google_discovery_add_data

    flags = google_discovery_add_data()
    assert flags, "expected --add-data for discovery_cache/documents"
    raw = flags[0].split("=", 1)[1]
    sep = ";" if ";" in raw else ":"
    src = Path(raw.split(sep, 1)[0])
    assert (src / "drive.v3.json").is_file()
