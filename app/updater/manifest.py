"""Fetch and parse OTA release manifest (latest.json)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version

from app.logging.setup import get_logger
from app.version import normalize_version

log = get_logger("updater.manifest")

ALLOWED_HOSTS = frozenset(
    {
        "github.com",
        "www.github.com",
        "objects.githubusercontent.com",
        "raw.githubusercontent.com",
    }
)


@dataclass
class WindowsZipAsset:
    url: str
    size: int
    sha256: str


@dataclass
class ReleaseManifest:
    schema: int
    version: str
    min_supported: str
    config_schema_version: int
    channel: str
    published_at: str
    windows_zip: WindowsZipAsset
    notes: str = ""
    config_migrations: list[str] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReleaseManifest:
        assets = data.get("assets") or {}
        win = assets.get("windows_zip") or {}
        return cls(
            schema=int(data.get("schema", 1)),
            version=str(data["version"]),
            min_supported=str(data.get("min_supported", "0.0.0")),
            config_schema_version=int(data.get("config_schema_version", 1)),
            channel=str(data.get("channel", "stable")),
            published_at=str(data.get("published_at", "")),
            windows_zip=WindowsZipAsset(
                url=str(win["url"]),
                size=int(win.get("size", 0)),
                sha256=str(win.get("sha256", "")).lower(),
            ),
            notes=str(data.get("notes", "")),
            config_migrations=list(data.get("config_migrations") or []),
        )


def validate_manifest_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Manifest URL must use HTTPS: {url}")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"Manifest host not allowed: {host}")


def validate_download_url(url: str) -> None:
    validate_manifest_url(url)


def default_manifest_url(github_repo: str) -> str:
    repo = github_repo.strip().strip("/")
    if not re.match(r"^[\w.-]+/[\w.-]+$", repo):
        raise ValueError(
            f"Invalid github_repo: {repo!r}. Use owner/repo in config [update].github_repo"
        )
    return f"https://github.com/{repo}/releases/latest/download/latest.json"


def fetch_manifest(url: str, timeout: float = 30.0) -> ReleaseManifest:
    validate_manifest_url(url)
    log.debug("Fetching manifest: {}", url)
    req = Request(url, headers={"User-Agent": "bgrec-updater/1.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(f"Could not fetch update manifest: {exc}") from exc
    manifest = ReleaseManifest.from_dict(data)
    manifest.version = normalize_version(manifest.version)
    manifest.min_supported = normalize_version(manifest.min_supported)
    validate_download_url(manifest.windows_zip.url)
    return manifest


def compare_versions(current: str, remote: str) -> int:
    """Return -1 if current < remote, 0 if equal, 1 if current > remote."""
    try:
        cur = Version(normalize_version(current))
        rem = Version(normalize_version(remote))
    except InvalidVersion as exc:
        raise ValueError(f"Invalid version string: {exc}") from exc
    if cur < rem:
        return -1
    if cur > rem:
        return 1
    return 0


def is_update_available(current: str, manifest: ReleaseManifest) -> bool:
    return compare_versions(current, manifest.version) < 0


def supports_upgrade(current: str, manifest: ReleaseManifest) -> bool:
    try:
        return Version(current) >= Version(manifest.min_supported)
    except InvalidVersion:
        return False
