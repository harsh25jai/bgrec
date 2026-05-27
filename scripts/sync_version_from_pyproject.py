#!/usr/bin/env python3
"""Sync app/version.py __version__ from pyproject.toml."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise SystemExit("version not found in pyproject.toml")
    return match.group(1).strip()


def main() -> None:
    version = read_pyproject_version()
    path = ROOT / "app" / "version.py"
    text = path.read_text(encoding="utf-8")
    new_text, n = re.subn(
        r'^__version__\s*=\s*"[^"]*"',
        f'__version__ = "{version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if n != 1:
        raise SystemExit("Could not update __version__ in app/version.py")
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        print(f"Synced app/version.py -> {version}")
    else:
        print(f"app/version.py already at {version}")


if __name__ == "__main__":
    main()
