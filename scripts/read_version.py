#!/usr/bin/env python3
"""Print project version from pyproject.toml (MAJOR.MINOR.PATCH). No package deps (CI tag job)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_pyproject_version_raw() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise SystemExit("version not found in pyproject.toml")
    return match.group(1).strip()


if __name__ == "__main__":
    sys.stdout.write(read_pyproject_version_raw())
