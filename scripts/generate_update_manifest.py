#!/usr/bin/env python3
"""Generate dist/latest.json for GitHub Release OTA."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import CONFIG_SCHEMA_VERSION  # noqa: E402
from app.version import normalize_version  # noqa: E402


def read_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.M)
    if not match:
        raise SystemExit("Could not read version from pyproject.toml")
    return normalize_version(match.group(1))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate OTA latest.json")
    parser.add_argument("--github-repo", default="", help="owner/repo (default: GITHUB_REPOSITORY)")
    parser.add_argument("--zip", default="dist/bgrec-Windows.zip", help="Path to release ZIP")
    parser.add_argument("--out", default="dist/latest.json", help="Output manifest path")
    parser.add_argument("--notes", default="", help="Release notes string")
    parser.add_argument("--min-supported", default="", help="Minimum app version (default: current)")
    args = parser.parse_args()

    repo = args.github_repo or __import__("os").environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        raise SystemExit("Set --github-repo or GITHUB_REPOSITORY")

    zip_path = (ROOT / args.zip).resolve()
    if not zip_path.exists():
        raise SystemExit(f"Missing ZIP: {zip_path}")

    version = read_version()
    tag = version if version.startswith("v") else f"v{version}"
    sha = sha256_file(zip_path)
    size = zip_path.stat().st_size
    min_supported = normalize_version(args.min_supported or "0.0.1")

    manifest = {
        "schema": 1,
        "version": version.lstrip("v"),
        "min_supported": min_supported,
        "config_schema_version": CONFIG_SCHEMA_VERSION,
        "channel": "stable",
        "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "assets": {
            "windows_zip": {
                "url": f"https://github.com/{repo}/releases/download/{tag}/bgrec-Windows.zip",
                "size": size,
                "sha256": sha,
            }
        },
        "notes": args.notes or f"bgrec {version}",
        "config_migrations": [],
    }

    out = (ROOT / args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    print(f"  version={manifest['version']} sha256={sha[:16]}… size={size}")


if __name__ == "__main__":
    main()
