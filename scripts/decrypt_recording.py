#!/usr/bin/env python3
"""Decrypt a .enc recording without rebuilding bgrec.exe.

Usage (from repo root, with deps installed):
  python scripts/decrypt_recording.py "C:\\path\\to\\rec_20250101.flac.enc"
  python scripts/decrypt_recording.py file.enc -o playback.flac

Uses: %LOCALAPPDATA%\\bgrec\\encryption.key
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.crypto.encryption import EncryptionManager


def default_key_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    base_dir = Path(base) / "bgrec"
    legacy = Path(base) / "BackgroundAudioRecorder"
    if not base_dir.exists() and legacy.exists():
        base_dir = legacy
    return base_dir / "encryption.key"


def main() -> int:
    parser = argparse.ArgumentParser(description="Decrypt a bgrec .enc audio file")
    parser.add_argument("encrypted", type=Path, help="Path to .enc file")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output audio file")
    parser.add_argument(
        "--key",
        type=Path,
        default=None,
        help="encryption.key path (default: %%LOCALAPPDATA%%\\bgrec\\encryption.key)",
    )
    args = parser.parse_args()

    enc_path = args.encrypted.expanduser().resolve()
    if not enc_path.is_file():
        print(f"ERROR: not found: {enc_path}", file=sys.stderr)
        return 1

    key_path = args.key or default_key_path()
    if not key_path.is_file():
        print(f"ERROR: missing key: {key_path}", file=sys.stderr)
        return 1

    out_path = args.output or enc_path.with_suffix("")
    mgr = EncryptionManager(key_path, enabled=True)
    mgr.decrypt_file(enc_path, out_path)
    print(f"Decrypted: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
