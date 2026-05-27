#!/usr/bin/env python3
"""Verify runtime version matches pyproject.toml (no generated version.py constant)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.version import get_version, read_version_from_pyproject  # noqa: E402


def main() -> None:
    pyproject_ver = read_version_from_pyproject()
    runtime_ver = get_version()
    if runtime_ver != pyproject_ver:
        raise SystemExit(
            f"Version mismatch: get_version()={runtime_ver!r} "
            f"pyproject.toml={pyproject_ver!r}"
        )
    print(f"Version OK: {runtime_ver} (from pyproject.toml)")


if __name__ == "__main__":
    main()
