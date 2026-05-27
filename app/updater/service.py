"""OTA check and automatic apply orchestration."""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from app.config.migrate import get_config_schema_version, load_config_meta
from app.config.settings import AppConfig, default_data_dirs, load_config, save_config
from app.logging.setup import get_logger
from app.updater.apply import apply_update, is_ota_target_install, read_current_meta
from app.updater.bundled import read_bundled_github_repo
from app.updater.manifest import (
    ReleaseManifest,
    default_manifest_url,
    fetch_manifest,
    is_update_available,
    supports_upgrade,
)
from app.version import get_version, normalize_version

log = get_logger("updater")


@dataclass
class UpdateCheckResult:
    current_version: str
    remote_version: str | None
    update_available: bool
    manifest: ReleaseManifest | None
    message: str
    manifest_url: str
    config_schema_version: int
    last_applied_version: str | None
    ota_capable: bool
    error: str | None = None


def ensure_update_repo(cfg: AppConfig, *, persist: bool = True) -> AppConfig:
    """Fill github_repo from CI-bundled file so users need not edit config."""
    if cfg.update.github_repo.strip():
        return cfg
    bundled = read_bundled_github_repo()
    if bundled:
        cfg.update.github_repo = bundled
        if persist:
            save_config(cfg)
            log.info("OTA: using bundled github_repo={}", bundled)
    return cfg


def resolve_manifest_url(cfg: AppConfig) -> str:
    if cfg.update.manifest_url.strip():
        return cfg.update.manifest_url.strip()
    cfg = ensure_update_repo(cfg, persist=False)
    if not cfg.update.github_repo.strip():
        raise ValueError(
            "OTA source unknown — rebuild with CI github-repo.txt or set [update].github_repo"
        )
    if cfg.update.channel == "test":
        raise ValueError("Test channel requires explicit [update].manifest_url")
    return default_manifest_url(cfg.update.github_repo)


def check_for_updates(cfg: AppConfig | None = None) -> UpdateCheckResult:
    cfg = ensure_update_repo(cfg or load_config())
    current = get_version()
    root = default_data_dirs()["root"]
    meta = load_config_meta(root)
    last_applied = read_current_meta().get("version") or meta.get("merged_from_version")
    if last_applied:
        try:
            last_applied = normalize_version(str(last_applied))
        except ValueError:
            pass

    if not cfg.update.enabled:
        return UpdateCheckResult(
            current_version=current,
            remote_version=None,
            update_available=False,
            manifest=None,
            message="Updates disabled in config ([update].enabled = false).",
            manifest_url="",
            config_schema_version=get_config_schema_version(),
            last_applied_version=last_applied,
            ota_capable=is_ota_target_install(),
        )

    try:
        url = resolve_manifest_url(cfg)
    except ValueError as exc:
        return UpdateCheckResult(
            current_version=current,
            remote_version=None,
            update_available=False,
            manifest=None,
            message=str(exc),
            manifest_url="",
            config_schema_version=get_config_schema_version(),
            last_applied_version=last_applied,
            ota_capable=is_ota_target_install(),
            error=str(exc),
        )

    try:
        manifest = fetch_manifest(url)
        remote_v = normalize_version(manifest.version)
        manifest.version = remote_v
    except Exception as exc:
        return UpdateCheckResult(
            current_version=current,
            remote_version=None,
            update_available=False,
            manifest=None,
            message=f"Update check failed: {exc}",
            manifest_url=url,
            config_schema_version=get_config_schema_version(),
            last_applied_version=last_applied,
            ota_capable=is_ota_target_install(),
            error=str(exc),
        )

    if not supports_upgrade(current, manifest):
        return UpdateCheckResult(
            current_version=current,
            remote_version=manifest.version,
            update_available=False,
            manifest=manifest,
            message=(
                f"Installed {current} is below min_supported {manifest.min_supported}. "
                "Manual reinstall required."
            ),
            manifest_url=url,
            config_schema_version=get_config_schema_version(),
            last_applied_version=last_applied,
            ota_capable=is_ota_target_install(),
        )

    available = is_update_available(current, manifest)
    msg = f"Update available: {current} → {manifest.version}" if available else f"Up to date ({current})"

    return UpdateCheckResult(
        current_version=current,
        remote_version=manifest.version,
        update_available=available,
        manifest=manifest,
        message=msg,
        manifest_url=url,
        config_schema_version=get_config_schema_version(),
        last_applied_version=last_applied,
        ota_capable=is_ota_target_install(),
    )


def spawn_unattended_update() -> None:
    """Launch a detached process to stop this daemon, apply OTA, and restart."""
    from app.install.portable import preferred_bgrec_executable

    exe = preferred_bgrec_executable()
    if getattr(sys, "frozen", False) or exe.name.lower() == "bgrec.exe":
        cmd = [str(exe), "update", "--yes", "--unattended"]
    else:
        cmd = [sys.executable, "-m", "app.cli.main", "update", "--yes", "--unattended"]

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    log.info("OTA: spawning unattended updater")
    subprocess.Popen(
        cmd,
        creationflags=creationflags,
        close_fds=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def try_auto_apply(cfg: AppConfig, result: UpdateCheckResult, *, unattended: bool) -> bool:
    """Apply update if available. Returns True if this process should exit (restarted elsewhere)."""
    if not result.update_available or not result.manifest:
        return False
    if not result.ota_capable:
        log.debug("OTA apply skipped: not a portable install")
        return False
    if not cfg.update.auto_apply and not unattended:
        return False

    log.info("OTA: applying {} → {}", result.current_version, result.manifest.version)
    applied = apply_update(result.manifest, force=unattended, restart=True)
    if applied.success:
        log.info("OTA: {}", applied.message)
        return True
    log.warning("OTA apply failed: {}", applied.message)
    return False


def run_startup_ota_if_needed() -> bool:
    """
    Run before the daemon starts recording.
    If an update is applied, a new daemon is spawned and this process should exit.
    """
    cfg = ensure_update_repo(load_config())
    if not cfg.update.enabled:
        return False
    if not cfg.update.check_on_start and not cfg.update.auto_apply:
        return False
    if not is_ota_target_install():
        return False

    result = check_for_updates(cfg)
    if result.error:
        log.debug("Startup OTA: {}", result.message)
        return False
    if not result.update_available:
        log.debug("Startup OTA: {}", result.message)
        return False
    if not cfg.update.auto_apply:
        log.info("OTA: {} (auto_apply is off)", result.message)
        return False

    return try_auto_apply(cfg, result, unattended=True)


def run_periodic_update_check() -> None:
    """Called from background scheduler while daemon is running."""
    cfg = ensure_update_repo(load_config())
    if not cfg.update.enabled or not cfg.update.auto_apply:
        return

    lock_path = default_data_dirs()["root"] / "updates" / ".ota-check.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = open(lock_path, "a+b")
        if sys.platform == "win32":
            import msvcrt

            try:
                msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                fd.close()
                return
        else:
            import fcntl

            try:
                fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fd.close()
                return
    except OSError:
        return

    try:
        result = check_for_updates(cfg)
        if not result.update_available or not result.manifest:
            return
        log.info("OTA: {}", result.message)
        spawn_unattended_update()
        time.sleep(2.0)
    finally:
        if sys.platform == "win32":
            import msvcrt

            try:
                msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        else:
            import fcntl

            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        fd.close()


def maybe_check_on_start(cfg: AppConfig, paths: dict[str, Path]) -> None:
    """Legacy hook — startup OTA runs earlier in run_foreground."""
    del cfg, paths
