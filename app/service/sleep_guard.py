"""Keep the system awake for recording and recover after sleep/hibernate (Windows)."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Callable

from app.logging.setup import get_logger

log = get_logger("sleep_guard")

# SetThreadExecutionState — prevent system sleep while recording
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040

# PowerRegisterSuspendResumeNotification (Windows 8+)
PBT_APMRESUMEAUTOMATIC = 0x12
PBT_APMRESUMESUSPEND = 0x7
PWR_REGISTER_SUSPEND_RESUME_FLAG = 0x00000002

_POWER_NOTIFY_CALLBACK = ctypes.WINFUNCTYPE(
    wintypes.ULONG,
    wintypes.LPVOID,
    wintypes.ULONG,
    wintypes.LPVOID,
)


class _DEVICE_NOTIFY_SUBSCRIBE_PARAMETERS(ctypes.Structure):
    _fields_ = [
        ("Callback", _POWER_NOTIFY_CALLBACK),
        ("Context", wintypes.LPVOID),
    ]


class SleepGuard:
    """
    While active, asks Windows not to enter system sleep so microphone capture can continue.

    The display may still turn off; the machine remains awake enough to record.
    If the PC does sleep (low battery, forced sleep), use coordinator resume logic to restart the mic.
    """

    def __init__(
        self,
        enabled: bool = True,
        on_resume: Callable[[], None] | None = None,
    ) -> None:
        self.enabled = enabled and sys.platform == "win32"
        self.on_resume = on_resume
        self._active = False
        self._registration: wintypes.HANDLE | None = None
        self._callback: _POWER_NOTIFY_CALLBACK | None = None
        self._kernel32 = ctypes.windll.kernel32 if sys.platform == "win32" else None
        self._powrprof = None
        if sys.platform == "win32":
            try:
                self._powrprof = ctypes.windll.powrprof
            except OSError:
                self._powrprof = None

    def acquire(self) -> None:
        if not self.enabled or self._active:
            return
        flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
        if self._kernel32.SetThreadExecutionState(flags) == 0:
            log.warning("SetThreadExecutionState failed — sleep may interrupt recording")
        else:
            log.info("Sleep inhibition on (system stays awake for recording; display may turn off)")
        self._register_resume_notify()
        self._active = True

    def release(self) -> None:
        if not self._active:
            return
        self._unregister_resume_notify()
        if self._kernel32:
            self._kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        self._active = False
        log.info("Sleep inhibition off")

    def _register_resume_notify(self) -> None:
        if not self._powrprof or not self.on_resume:
            return

        def _handler(_context, event_type, _setting) -> int:
            if event_type in (PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC):
                log.info("Resumed from sleep/hibernate (event={:#x})", event_type)
                try:
                    self.on_resume()
                except Exception as exc:
                    log.exception("Resume handler failed: {}", exc)
            return 0

        self._callback = _POWER_NOTIFY_CALLBACK(_handler)
        params = _DEVICE_NOTIFY_SUBSCRIBE_PARAMETERS(self._callback, None)
        handle = wintypes.HANDLE()
        hr = self._powrprof.PowerRegisterSuspendResumeNotification(
            PWR_REGISTER_SUSPEND_RESUME_FLAG,
            ctypes.byref(params),
            ctypes.byref(handle),
        )
        if hr == 0:
            self._registration = handle
            log.debug("Registered for power resume notifications")
        else:
            log.debug("Power resume registration failed (hr={:#x})", hr & 0xFFFFFFFF)

    def _unregister_resume_notify(self) -> None:
        if self._registration and self._powrprof:
            try:
                self._powrprof.PowerUnregisterSuspendResumeNotification(self._registration)
            except Exception:
                pass
        self._registration = None
        self._callback = None
