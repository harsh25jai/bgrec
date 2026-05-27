"""Application version (keep in sync with pyproject.toml — use MAJOR.MINOR.PATCH e.g. 0.0.1)."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from packaging.version import InvalidVersion, Version

__version__ = "0.0.1"


def normalize_version(raw: str) -> str:
    """
    Canonical three-part version: 0.0.1
    Accepts optional leading 'v'.
    """
    text = raw.strip().lstrip("vV")
    if not text:
        raise ValueError("Empty version")
    try:
        release = Version(text).release
    except InvalidVersion as exc:
        raise ValueError(f"Invalid version {raw!r}: {exc}") from exc
    major = release[0] if len(release) > 0 else 0
    minor = release[1] if len(release) > 1 else 0
    patch = release[2] if len(release) > 2 else 0
    return f"{major}.{minor}.{patch}"


@lru_cache(maxsize=1)
def get_version() -> str:
    """Installed package version (always MAJOR.MINOR.PATCH)."""
    raw: str | None = None
    try:
        from importlib.metadata import version as pkg_version

        raw = pkg_version("bgrec")
    except Exception:
        pass

    if not raw:
        root = Path(__file__).resolve().parents[1]
        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            match = re.search(
                r'^\s*version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), re.M
            )
            if match:
                raw = match.group(1)

    if not raw:
        raw = __version__
    return normalize_version(raw)
