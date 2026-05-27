#!/usr/bin/env python3
"""Verify all runtime and build dependencies import correctly."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"

ROOT = Path(__file__).resolve().parents[1]

# Modules required for PyInstaller build and CLI.
MODULES = [
    "PyInstaller",
    "typer",
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
    "watchdog",
    "cryptography",
    "googleapiclient",
    "googleapiclient.discovery",
    "google_auth_oauthlib",
    "google_auth_oauthlib.flow",
    "google.oauth2.credentials",
    "google.auth.transport.requests",
    "httplib2",
    "uritemplate",
    "tomli_w",
    "certifi",
    "packaging",
]


def main() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    failed: list[str] = []
    for name in MODULES:
        try:
            importlib.import_module(name)
            print(f"  OK  {name}")
        except ImportError as exc:
            if name == "pydub" and "pyaudioop" in str(exc):
                print(f"  WARN {name}: {exc} (use Python 3.11-3.12 on Windows)")
                continue
            print(f"  FAIL {name}: {exc}")
            failed.append(name)

    print()
    if IS_WINDOWS:
        try:
            importlib.import_module("app.cli.main")
            print("  OK  app.cli.main")
        except Exception as exc:
            print(f"  FAIL app.cli.main: {exc}")
            failed.append("app.cli.main")
    else:
        for mod in ("app.config.settings", "app.recorder.converter", "app.crypto.encryption"):
            try:
                importlib.import_module(mod)
                print(f"  OK  {mod}")
            except Exception as exc:
                print(f"  FAIL {mod}: {exc}")
                failed.append(mod)
        print("  --  (full app.cli.main requires Windows)")

    if failed:
        print("\nMissing packages. From repo root run:")
        print("  pip install -r requirements-windows.txt")
        print("  pip install -e .")
        print("\nFailed:", ", ".join(failed))
        return 1

    print("\nAll dependency checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
