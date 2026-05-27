"""OTA portable install path and version resolution."""

from __future__ import annotations

from pathlib import Path

from app.install.portable import (
    get_installed_version_for_ota,
    is_running_installed_binary,
    portable_install_exists,
    wrong_executable_hint,
)
from app.updater.apply import is_ota_target_install, write_current_meta
from app.updater.manifest import compare_versions


def test_compare_versions_patch_bump() -> None:
    assert compare_versions("0.0.1", "0.0.2") == -1


def test_ota_target_without_bin_on_non_windows(monkeypatch) -> None:
    monkeypatch.setattr("app.updater.apply.sys.platform", "darwin")
    monkeypatch.setattr("app.updater.apply.portable_install_exists", lambda: False)
    assert is_ota_target_install() is False


def test_wrong_executable_hint_only_when_mismatch(monkeypatch) -> None:
    monkeypatch.setattr("app.install.portable.portable_install_exists", lambda: True)
    monkeypatch.setattr("app.install.portable.is_running_installed_binary", lambda: False)
    hint = wrong_executable_hint()
    assert hint is not None
    assert "bgrec\\bin" in hint or "bgrec/bin" in hint


def test_get_installed_version_prefers_meta(monkeypatch, tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    bin_exe = bin_dir / "bgrec.exe"
    bin_exe.write_bytes(b"stub")

    def fake_dirs() -> dict[str, Path]:
        return {
            "root": tmp_path,
            "recordings": tmp_path / "recordings",
            "cache": tmp_path / "cache",
            "logs": tmp_path / "logs",
            "pending_uploads": tmp_path / "cache" / "pending",
            "credentials": tmp_path / "credentials",
        }

    monkeypatch.setattr("app.install.portable.bin_exe_path", lambda: bin_exe)
    monkeypatch.setattr("app.install.portable.portable_install_exists", lambda: True)
    monkeypatch.setattr("app.install.portable.probe_frozen_exe_version", lambda _p: None)
    monkeypatch.setattr("app.updater.apply.default_data_dirs", fake_dirs)

    write_current_meta("0.0.2", 1)
    assert get_installed_version_for_ota() == "0.0.2"


def test_running_installed_binary_when_same_path(monkeypatch, tmp_path: Path) -> None:
    exe = tmp_path / "bgrec.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr("app.install.portable.bin_exe_path", lambda: exe)
    monkeypatch.setattr("app.install.portable.portable_install_exists", lambda: True)
    monkeypatch.setattr("sys.executable", str(exe))
    assert is_running_installed_binary() is True
    assert wrong_executable_hint() is None
