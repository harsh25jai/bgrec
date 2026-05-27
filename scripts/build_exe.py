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
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only run dependency verification (no PyInstaller)",
    )
    args = parser.parse_args()

    if args.check_only:
        from scripts.pyinstaller_build import check_build_prereqs

        check_build_prereqs()
        print("Dependency check OK — ready to build.")
        return

    exe = run_build(verify=not args.no_verify)
    print(f"\nBuild complete: {exe}")


if __name__ == "__main__":
    main()
