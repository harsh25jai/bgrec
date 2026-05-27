"""Verify downloaded OTA artifacts."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: Path, expected: str) -> None:
    expected = expected.lower().strip()
    if not expected:
        raise ValueError("Manifest missing sha256 for windows_zip")
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f"SHA256 mismatch for {path.name}: expected {expected}, got {actual}")


def verify_size(path: Path, expected: int) -> None:
    if expected <= 0:
        return
    actual = path.stat().st_size
    if actual != expected:
        raise ValueError(f"Size mismatch for {path.name}: expected {expected}, got {actual}")
