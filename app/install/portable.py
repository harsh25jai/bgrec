"""Resolve the portable install binary vs a one-off copy (e.g. Downloads folder)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app.config.settings import default_data_dirs
from app.version import get_version, normalize_version


def bin_exe_path() -> Path:
    return default_data_dirs()["root"] / "bin" / "bgrec.exe"


def portable_install_exists() -> bool:
    return bin_exe_path().is_file()


def preferred_bgrec_executable() -> Path:
    """Daemon, startup, and post-OTA restart should use the installed portable binary."""
    bin_exe = bin_exe_path()
    if bin_exe.is_file():
        return bin_exe.resolve()
    return Path(sys.executable).resolve()


def is_running_installed_binary() -> bool:
    if not portable_install_exists():
        return False
    try:
        return Path(sys.executable).resolve() == bin_exe_path().resolve()
    except OSError:
        return False


def probe_frozen_exe_version(exe: Path) -> str | None:
    if not exe.is_file():
        return None
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            [str(exe), "version", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=90,
            creationflags=flags,
        )
        if result.returncode == 0:
            line = (result.stdout or "").strip().splitlines()
            if line:
                return normalize_version(line[0])
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return None


def get_portable_bin_version() -> str | None:
    """Version of bgrec.exe under %LOCALAPPDATA%\\bgrec\\bin (may differ from this process)."""
    bin_exe = bin_exe_path()
    if not bin_exe.is_file():
        return None
    from app.updater.apply import read_current_meta
    from app.updater.manifest import compare_versions

    candidates: list[str] = []
    probed = probe_frozen_exe_version(bin_exe)
    if probed:
        candidates.append(probed)
    meta = read_current_meta().get("version")
    if meta:
        try:
            candidates.append(normalize_version(str(meta)))
        except ValueError:
            pass
    if not candidates:
        return None
    best = candidates[0]
    for ver in candidates[1:]:
        if compare_versions(ver, best) > 0:
            best = ver
    return best


def get_installed_version_for_ota() -> str:
    """
    Version to compare against the remote manifest.
    Uses the portable bin when installed (not the Downloads copy path).
    Prefers the highest of probed binary vs last successful OTA meta (avoids re-download loops).
    """
    if portable_install_exists():
        bin_ver = get_portable_bin_version()
        if bin_ver:
            return bin_ver
    return get_version()


def wrong_executable_hint() -> str | None:
    if is_running_installed_binary() or not portable_install_exists():
        return None
    bin_exe = bin_exe_path()
    return (
        f"OTA updated {bin_exe}, but this command used {Path(sys.executable)}. "
        f'Run: "{bin_exe}" status   or open a new terminal (PATH should use ...\\bgrec\\bin).'
    )
