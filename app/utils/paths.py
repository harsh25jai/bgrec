"""Safe path validation for file operations."""

from __future__ import annotations

from pathlib import Path


def is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def safe_resolve(path: Path, base: Path) -> Path:
    resolved = path.resolve()
    if not is_under(resolved, base):
        raise ValueError(f"Path escapes allowed directory: {path}")
    return resolved
