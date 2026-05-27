"""Tests for OTA manifest version comparison."""

from __future__ import annotations

from app.updater.manifest import (
    ReleaseManifest,
    WindowsZipAsset,
    compare_versions,
    is_update_available,
)


def _manifest(version: str) -> ReleaseManifest:
    return ReleaseManifest(
        schema=1,
        version=version,
        min_supported="1.0.0",
        config_schema_version=1,
        channel="stable",
        published_at="",
        windows_zip=WindowsZipAsset(url="https://github.com/a/b/releases/download/v1/x.zip", size=1, sha256="ab"),
    )


def test_compare_versions() -> None:
    assert compare_versions("0.0.1", "0.0.2") == -1
    assert compare_versions("0.0.2", "0.0.1") == 1
    assert compare_versions("0.0.1", "0.0.1") == 0


def test_update_available() -> None:
    assert is_update_available("0.0.1", _manifest("0.0.2"))
    assert not is_update_available("0.0.2", _manifest("0.0.1"))
