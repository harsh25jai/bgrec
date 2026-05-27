"""Detect files locked by another process (Windows sharing violation)."""

from __future__ import annotations


def is_file_in_use(exc: BaseException) -> bool:
    if isinstance(exc, PermissionError):
        return True
    if isinstance(exc, OSError):
        if exc.errno == 13:
            return True
        if getattr(exc, "winerror", None) == 32:
            return True
    return False
