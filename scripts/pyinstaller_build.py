"""Shared PyInstaller settings for local Windows builds and CI."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"
ENTRY = ROOT / "app" / "cli" / "main.py"

# PyInstaller often misses these (CLI + Google + audio stack).
HIDDEN_IMPORTS = [
    "app.cli.main",
    "typer",
    "typer.core",
    "typer.main",
    "typer.models",
    "click",
    "shellingham",
    "typing_extensions",
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
    "packaging",
    "app.version",
    "app.config.migrate",
    "app.updater.manifest",
    "app.updater.download",
    "app.updater.verify",
    "app.updater.apply",
    "app.updater.service",
    "app.updater.bundled",
    "app.updater.scheduler",
    "app.runtime_bootstrap",
    "app.install.portable",
    "certifi",
]

# collect-all bundles package data; avoid copy-metadata (often breaks on Windows).
COLLECT_ALL = [
    "typer",
    "click",
    "rich",
    "sounddevice",
    "cryptography",
    "certifi",
    "googleapiclient",
    "google_auth_oauthlib",
]


def check_build_prereqs() -> None:
    """Fail fast with a clear message before PyInstaller runs."""
    verify_script = ROOT / "scripts" / "verify_deps.py"
    result = subprocess.run(
        [sys.executable, str(verify_script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        output = (result.stdout or "") + (result.stderr or "")
        raise RuntimeError(
            "Dependency check failed before PyInstaller.\n\n"
            f"{output}\n"
            "Fix:\n"
            "  pip install -r requirements-windows.txt\n"
            "  pip install -e .\n"
            "  python scripts/verify_deps.py\n"
        )


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
    sep = os.pathsep
    pyproject = ROOT / "pyproject.toml"
    if pyproject.exists():
        cmd.append(f"--add-data={pyproject}{sep}.")
    for name in ("config.toml.example", "schema-version.txt", "github-repo.txt"):
        src = ROOT / "config" / name
        if src.exists():
            cmd.append(f"--add-data={src}{sep}config")
    cmd.append(str(ENTRY))
    return cmd


def verify_build(exe: Path) -> None:
    """Smoke test: bundled exe should show CLI help without import errors."""
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
            f"Build verification failed (exit {result.returncode}).\n"
            f"{combined[:3000]}\n\n"
            "If PyInstaller succeeded, try: python scripts/build_exe.py --no-verify"
        )


def run_build(*, verify: bool = True) -> Path:
    if sys.platform != "win32":
        raise RuntimeError(
            "PyInstaller cannot create a Windows .exe on macOS/Linux.\n"
            "From Mac, run:  ./scripts/build-windows-from-mac.sh\n"
            "That builds on GitHub Actions (Windows runner) and downloads the ZIP."
        )

    check_build_prereqs()
    cmd = pyinstaller_command()
    print("Running PyInstaller (this may take a few minutes)...")
    print("Command:", " ".join(cmd))

    log_file = BUILD / "pyinstaller-last.log"
    BUILD.mkdir(parents=True, exist_ok=True)
    try:
        with log_file.open("w", encoding="utf-8") as log:
            subprocess.check_call(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as exc:
        tail = ""
        if log_file.exists():
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = "\n".join(lines[-40:])
        raise RuntimeError(
            f"PyInstaller failed (exit {exc.returncode}).\n"
            f"Full log: {log_file}\n\n"
            f"Last lines:\n{tail}"
        ) from exc

    exe = DIST / "bgrec.exe"
    if not exe.exists():
        raise FileNotFoundError(f"Expected output not found: {exe}")

    if verify:
        print("Verifying bundled exe...")
        try:
            verify_build(exe)
            print("Verification OK")
        except RuntimeError:
            print(
                "WARNING: verification failed but bgrec.exe was created.\n"
                "  Test manually: dist\\bgrec.exe --help\n"
                "  Or rebuild with: python scripts/build_exe.py --no-verify",
                file=sys.stderr,
            )
            raise

    return exe
