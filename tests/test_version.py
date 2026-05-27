"""Version is read from pyproject.toml only."""

from __future__ import annotations

from pathlib import Path

from app.version import get_version, read_version_from_pyproject


def test_read_version_from_pyproject_matches_pyproject_file() -> None:
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    import re

    match = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match
    assert read_version_from_pyproject() == match.group(1)


def test_get_version_matches_pyproject() -> None:
    assert get_version() == read_version_from_pyproject()
