"""Build standalone Windows executable with PyInstaller (Windows only)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.pyinstaller_build import run_build

if __name__ == "__main__":
    exe = run_build()
    print(f"\nBuild complete: {exe}")
