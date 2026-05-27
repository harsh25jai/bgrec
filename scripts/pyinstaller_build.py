"""Shared PyInstaller settings for local Windows builds and CI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"
ENTRY = ROOT / "app" / "cli" / "main.py"


def pyinstaller_command() -> list[str]:
    return [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        "bgrec",
        "--onefile",
        "--console",
        "--clean",
        "--noconfirm",
        f"--distpath={DIST}",
        f"--workpath={BUILD}",
        "--hidden-import=googleapiclient.discovery",
        "--hidden-import=google_auth_oauthlib.flow",
        "--hidden-import=google.oauth2.credentials",
        "--hidden-import=sounddevice",
        "--hidden-import=_sounddevice_data",
        "--collect-all=sounddevice",
        str(ENTRY),
    ]


def run_build() -> Path:
    if sys.platform != "win32":
        raise RuntimeError(
            "PyInstaller cannot create a Windows .exe on macOS/Linux.\n"
            "From Mac, run:  ./scripts/build-windows-from-mac.sh\n"
            "That builds on GitHub Actions (Windows runner) and downloads the ZIP."
        )
    cmd = pyinstaller_command()
    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)
    exe = DIST / "bgrec.exe"
    if not exe.exists():
        raise FileNotFoundError(f"Expected output not found: {exe}")
    return exe
