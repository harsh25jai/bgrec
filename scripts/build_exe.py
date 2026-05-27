"""Build standalone Windows executable with PyInstaller (Windows only)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.pyinstaller_build import run_build


def main() -> None:
    parser = argparse.ArgumentParser(description="Build bgrec.exe with PyInstaller")
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip post-build smoke test (dist\\bgrec.exe --help)",
    )
    args = parser.parse_args()
    exe = run_build(verify=not args.no_verify)
    print(f"\nBuild complete: {exe}")


if __name__ == "__main__":
    main()
