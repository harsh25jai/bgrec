"""Download OTA release assets."""

from __future__ import annotations

import shutil
from pathlib import Path
from urllib.request import Request, urlopen

from app.updater.manifest import validate_download_url


def download_file(url: str, dest: Path, timeout: float = 300.0) -> Path:
    validate_download_url(url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = Request(url, headers={"User-Agent": "bgrec-updater/1.0"})
    with urlopen(req, timeout=timeout) as resp, tmp.open("wb") as out:
        shutil.copyfileobj(resp, out, length=1024 * 256)
    tmp.replace(dest)
    return dest
