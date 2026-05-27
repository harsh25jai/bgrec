"""Single background daemon instance (Windows named mutex)."""

from __future__ import annotations

import sys

MUTEX_NAME = r"Local\bgrec-recording-daemon-v1"
ERROR_ALREADY_EXISTS = 183


class DaemonInstanceLock:
    """Held for the lifetime of the recording coordinator process."""

    def __init__(self) -> None:
        self._handle: int | None = None

    def acquire(self) -> bool:
        if sys.platform != "win32":
            return True
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetLastError(0)
        handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
        if not handle:
            return False
        already = kernel32.GetLastError() == ERROR_ALREADY_EXISTS
        if already:
            kernel32.CloseHandle(handle)
            self._handle = None
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if sys.platform != "win32" or not self._handle:
            return
        import ctypes

        ctypes.windll.kernel32.CloseHandle(self._handle)
        self._handle = None

    def __enter__(self) -> DaemonInstanceLock:
        if not self.acquire():
            raise RuntimeError("Another bgrec recording daemon is already running")
        return self

    def __exit__(self, *args: object) -> None:
        self.release()


def is_daemon_lock_held() -> bool:
    """True if a coordinator currently holds the daemon mutex."""
    if sys.platform != "win32":
        return False
    import ctypes

    kernel32 = ctypes.windll.kernel32
    SYNCHRONIZE = 0x00100000
    handle = kernel32.OpenMutexW(SYNCHRONIZE, False, MUTEX_NAME)
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return False
