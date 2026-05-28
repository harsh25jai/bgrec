"""Windows subprocess flags to avoid console window flashes."""

from __future__ import annotations

import subprocess
import sys

# subprocess.CREATE_NO_WINDOW exists on Python 3.7+ Windows; fallback for typing/tools.
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def no_window_creationflags(*, detached: bool = False) -> int:
    """Creation flags for child processes that must not flash a console."""
    if sys.platform != "win32":
        return 0
    flags = CREATE_NO_WINDOW
    if detached:
        flags |= subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    return flags
