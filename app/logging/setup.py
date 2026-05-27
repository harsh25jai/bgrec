"""Structured logging with rotating files via loguru."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

_CONFIGURED = False


def configure_logging(log_dir: Path, level: str = "INFO", max_bytes: int = 5_242_880, backup_count: int = 5) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_dir.mkdir(parents=True, exist_ok=True)
    logger.remove()

    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    logger.add(sys.stderr, level=level, format=fmt, enqueue=True)

    logger.add(
        log_dir / "app.log",
        level=level,
        format=fmt,
        rotation=max_bytes,
        retention=backup_count,
        compression="zip",
        enqueue=True,
        serialize=False,
    )

    logger.add(
        log_dir / "upload.log",
        level="INFO",
        format=fmt,
        rotation=max_bytes,
        retention=backup_count,
        filter=lambda record: "upload" in record["extra"],
        enqueue=True,
    )

    logger.add(
        log_dir / "errors.log",
        level="ERROR",
        format=fmt,
        rotation=max_bytes,
        retention=backup_count,
        enqueue=True,
    )

    _CONFIGURED = True


def get_logger(name: str):
    return logger.bind(module=name)
