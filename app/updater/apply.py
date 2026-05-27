"""Apply OTA update on Windows portable installs."""

from __future__ import annotations

import json
import shutil
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app.config.migrate import merge_config_defaults
from app.config.settings import default_config_path, default_data_dirs
from app.logging.setup import get_logger
from app.service.daemon import StopResult, stop_daemon
from app.updater.download import download_file
from app.updater.manifest import ReleaseManifest
from app.updater.verify import verify_sha256, verify_size

log = get_logger("updater.apply")

CURRENT_META = "current.json"


@dataclass
class ApplyResult:
    success: bool
    message: str
    installed_version: str | None = None
    backup_exe: Path | None = None


def updates_root() -> Path:
    return default_data_dirs()["root"] / "updates"


def bin_exe_path() -> Path:
    return default_data_dirs()["root"] / "bin" / "bgrec.exe"


def is_ota_target_install() -> bool:
    """True when this process can replace the installed portable binary."""
    if sys.platform != "win32":
        return False
    exe = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False):
        return True
    expected = bin_exe_path()
    try:
        return exe == expected.resolve()
    except OSError:
        return expected.exists() and exe.name.lower() == "bgrec.exe"


def write_current_meta(version: str, config_schema_version: int) -> None:
    root = updates_root()
    root.mkdir(parents=True, exist_ok=True)
    meta = {
        "version": version,
        "applied_at": time.time(),
        "config_schema_version": config_schema_version,
    }
    (root / CURRENT_META).write_text(json.dumps(meta, indent=2), encoding="utf-8")


def read_current_meta() -> dict:
    path = updates_root() / CURRENT_META
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def rollback_exe() -> ApplyResult:
    bin_exe = bin_exe_path()
    backup = bin_exe.with_name("bgrec.exe.bak")
    if not backup.exists():
        return ApplyResult(False, "No backup executable (bgrec.exe.bak) found.")
    shutil.copy2(backup, bin_exe)
    return ApplyResult(True, f"Restored {bin_exe} from backup.", backup_exe=backup)


def apply_update(
    manifest: ReleaseManifest,
    *,
    force: bool = False,
    restart: bool = True,
) -> ApplyResult:
    if not is_ota_target_install():
        return ApplyResult(
            False,
            "OTA apply is only supported for the portable bgrec.exe install "
            f"({bin_exe_path()}). Dev installs: git pull && pip install -e .",
        )

    if manifest.channel == "test":
        return ApplyResult(False, "Refusing to apply test-channel manifest on stable install.")

    stop = stop_daemon()
    if stop == StopResult.FAILED:
        if not force:
            return ApplyResult(
                False,
                "Could not stop bgrec daemon. Run: bgrec stop   or use --force.",
            )

    root = updates_root()
    downloads = root / "downloads"
    staging = root / "staging" / manifest.version
    zip_path = downloads / f"bgrec-{manifest.version}.zip"

    try:
        log.info("Downloading {}", manifest.windows_zip.url)
        download_file(manifest.windows_zip.url, zip_path)
        verify_sha256(zip_path, manifest.windows_zip.sha256)
        verify_size(zip_path, manifest.windows_zip.size)

        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(staging)

        staged_exe = staging / "bgrec.exe"
        if not staged_exe.exists():
            return ApplyResult(False, f"ZIP missing bgrec.exe: {zip_path}")

        bin_exe = bin_exe_path()
        bin_exe.parent.mkdir(parents=True, exist_ok=True)
        backup = bin_exe.with_name("bgrec.exe.bak")
        if bin_exe.exists():
            shutil.copy2(bin_exe, backup)

        new_exe = bin_exe.with_name("bgrec.exe.new")
        shutil.copy2(staged_exe, new_exe)
        new_exe.replace(bin_exe)

        example = staging / "config.toml.example"
        if not example.exists():
            example = staging / "config" / "config.toml.example"
        if example.exists():
            merge = merge_config_defaults(
                default_config_path(),
                example,
                merged_from_version=manifest.version,
            )
            log.info("Config migrate: {} keys added", len(merge.keys_added))

        write_current_meta(manifest.version, manifest.config_schema_version)

        if restart:
            from app.service.daemon import spawn_background

            spawn_background()

        return ApplyResult(
            True,
            f"Updated to {manifest.version}",
            installed_version=manifest.version,
            backup_exe=backup if backup.exists() else None,
        )
    except Exception as exc:
        log.exception("OTA apply failed: {}", exc)
        backup = bin_exe_path().with_name("bgrec.exe.bak")
        if backup.exists() and not bin_exe_path().exists():
            shutil.copy2(backup, bin_exe_path())
        return ApplyResult(False, str(exc))
