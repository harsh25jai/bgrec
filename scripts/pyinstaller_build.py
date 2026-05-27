"""Shared PyInstaller settings for local Windows builds and CI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"
ENTRY = ROOT / "app" / "cli" / "main.py"

# Packages PyInstaller often misses (dynamic imports / metadata).
HIDDEN_IMPORTS = [
    "app",
    "app.cli.main",
    "app.config.settings",
    "app.recorder.audio_recorder",
    "app.recorder.converter",
    "app.scheduler.coordinator",
    "app.service.daemon",
    "app.service.state",
    "app.service.watchdog",
    "app.startup.windows_startup",
    "app.uploader.drive_client",
    "app.uploader.upload_queue",
    "app.crypto.encryption",
    "app.retention.cleanup",
    "app.logging.setup",
    "app.platform_check",
    "typer",
    "typer.core",
    "typer.main",
    "typer.models",
    "click",
    "shellingham",
    "rich",
    "rich.console",
    "rich.table",
    "loguru",
    "numpy",
    "pydub",
    "sounddevice",
    "_sounddevice_data",
    "watchdog",
    "watchdog.observers",
    "watchdog.events",
    "cryptography",
    "cryptography.hazmat.primitives.ciphers.aead",
    "googleapiclient",
    "googleapiclient.discovery",
    "google_auth_oauthlib",
    "google_auth_oauthlib.flow",
    "google.oauth2.credentials",
    "google.auth.transport.requests",
    "httplib2",
    "uritemplate",
    "tomli_w",
]

COLLECT_ALL = [
    "typer",
    "click",
    "rich",
    "sounddevice",
    "cryptography",
    "googleapiclient",
    "google_auth_oauthlib",
    "numpy",
]

COLLECT_SUBMODULES = [
    "app",
    "googleapiclient",
]


def pyinstaller_command() -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        "bgrec",
        "--onefile",
        "--console",
        "--clean",
        "--noconfirm",
        f"--paths={ROOT}",
        f"--distpath={DIST}",
        f"--workpath={BUILD}",
    ]
    for mod in HIDDEN_IMPORTS:
        cmd.append(f"--hidden-import={mod}")
    for pkg in COLLECT_ALL:
        cmd.append(f"--collect-all={pkg}")
    for pkg in COLLECT_SUBMODULES:
        cmd.append(f"--collect-submodules={pkg}")
    for pkg in ("typer", "rich", "click"):
        cmd.append(f"--copy-metadata={pkg}")
    cmd.append(str(ENTRY))
    return cmd


def verify_build(exe: Path) -> None:
    """Quick smoke test: bundled exe must import typer."""
    result = subprocess.run(
        [str(exe), "--help"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=ROOT,
    )
    combined = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0 or "No module named" in combined:
        raise RuntimeError(
            f"Build verification failed (exit {result.returncode}).\n{combined[:2000]}"
        )


def run_build(*, verify: bool = True) -> Path:
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
    if verify:
        print("Verifying bundled exe...")
        verify_build(exe)
        print("Verification OK")
    return exe
