"""Build-time bundled metadata for zero-config OTA."""

from __future__ import annotations

import sys
from pathlib import Path


def _resource_roots() -> list[Path]:
    roots: list[Path] = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        roots.append(Path(sys._MEIPASS))
    roots.append(Path(__file__).resolve().parents[2])
    return roots


def read_bundled_github_repo() -> str:
    """owner/repo written at CI build into config/github-repo.txt."""
    for root in _resource_roots():
        path = root / "config" / "github-repo.txt"
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "YOUR_GITHUB" not in line and "/" in line:
                    return line
    env = __import__("os").environ.get("BGREC_GITHUB_REPO", "").strip()
    return env if env and "/" in env else ""
