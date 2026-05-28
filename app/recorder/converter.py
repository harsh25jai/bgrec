"""Convert WAV chunks to FLAC or MP3 using pydub (requires ffmpeg on PATH)."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from app.logging.setup import get_logger
from app.utils.windows_process import CREATE_NO_WINDOW

log = get_logger("converter")


def _patch_pydub_subprocess_no_console() -> None:
    """ffmpeg invocations via pydub must not flash a console window on Windows."""
    if sys.platform != "win32":
        return
    import subprocess as sp
    from pydub import utils as pydub_utils

    if getattr(pydub_utils, "_bgrec_no_console_patched", False):
        return

    _original = sp.Popen

    def _popen(*args, **kwargs):
        flags = kwargs.get("creationflags", 0)
        kwargs["creationflags"] = flags | CREATE_NO_WINDOW
        return _original(*args, **kwargs)

    sp.Popen = _popen  # type: ignore[misc,assignment]
    pydub_utils.Popen = _popen  # type: ignore[misc,assignment]
    pydub_utils._bgrec_no_console_patched = True


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def wav_to_compressed(
    wav_path: Path,
    output_format: str = "flac",
    mp3_bitrate: str = "64k",
) -> Path:
    if not ffmpeg_available():
        log.warning("ffmpeg not found on PATH; keeping WAV")
        return wav_path

    # Lazy import: pydub prints a RuntimeWarning on import if ffmpeg is missing.
    from pydub import AudioSegment

    _patch_pydub_subprocess_no_console()
    audio = AudioSegment.from_wav(str(wav_path))
    fmt = output_format.lower()
    out_path = wav_path.with_suffix(f".{fmt}")

    export_kwargs: dict = {}
    if fmt == "mp3":
        export_kwargs["bitrate"] = mp3_bitrate
    elif fmt == "flac":
        export_kwargs["parameters"] = ["-compression_level", "8"]

    audio.export(str(out_path), format=fmt, **export_kwargs)
    wav_path.unlink(missing_ok=True)
    log.debug("Converted {} to {}", wav_path.stem, out_path.name)
    return out_path
