"""Ensure the app runs only on supported Windows versions."""

from __future__ import annotations

import sys


def require_windows() -> None:
    if sys.platform != "win32":
        raise RuntimeError("This application supports Windows 10/11 only.")
    version = sys.getwindowsversion()  # type: ignore[attr-defined]
    if version.major < 10:
        raise RuntimeError("Windows 10 or later is required.")
