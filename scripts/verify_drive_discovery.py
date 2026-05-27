#!/usr/bin/env python3
"""Fail if Google Drive v3 static discovery document is missing (PyInstaller / install QA)."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from googleapiclient.discovery_cache import get_static_doc
    except ImportError as exc:
        print(f"googleapiclient not installed: {exc}", file=sys.stderr)
        return 1

    doc = get_static_doc("drive", "v3")
    if not doc:
        print(
            "drive.v3 discovery JSON not found. "
            "Reinstall google-api-python-client or fix PyInstaller --add-data for "
            "googleapiclient/discovery_cache/documents.",
            file=sys.stderr,
        )
        return 1

    if '"drive"' not in doc.lower() and '"name"' not in doc:
        print("drive.v3 discovery document looks invalid", file=sys.stderr)
        return 1

    print("OK: drive.v3 discovery document available")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
