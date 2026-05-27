"""Application version (single source: pyproject.toml [project].version)."""

from __future__ import annotations

import re
import sys
from functools import lru_cache
from pathlib import Path

from packaging.version import InvalidVersion, Version

_REPO_ROOT = Path(__file__).resolve().parents[1]
_VERSION_PATTERN = re.compile(r'^\s*version\s*=\s*"([^"]+)"', re.MULTILINE)


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


def _pyproject_candidates() -> list[Path]:
    paths: list[Path] = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        paths.append(Path(sys._MEIPASS) / "pyproject.toml")
    paths.append(_REPO_ROOT / "pyproject.toml")
    return paths


@lru_cache(maxsize=1)
def read_version_from_pyproject() -> str:
    """Read and normalize [project].version from pyproject.toml."""
    for path in _pyproject_candidates():
        if not path.is_file():
            continue
        match = _VERSION_PATTERN.search(path.read_text(encoding="utf-8"))
        if match:
            return normalize_version(match.group(1))
    raise RuntimeError(
        "Could not read version from pyproject.toml "
        f"(checked: {', '.join(str(p) for p in _pyproject_candidates())})"
    )


@lru_cache(maxsize=1)
def get_version() -> str:
    """Installed package version (always MAJOR.MINOR.PATCH)."""
    try:
        from importlib.metadata import version as pkg_version

        return normalize_version(pkg_version("bgrec"))
    except Exception:
        return read_version_from_pyproject()


def __getattr__(name: str) -> str:
    if name == "__version__":
        return get_version()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
