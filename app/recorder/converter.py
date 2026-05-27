"""Convert WAV chunks to FLAC or MP3 using pydub (requires ffmpeg on PATH)."""

from __future__ import annotations

import shutil
from pathlib import Path

from pydub import AudioSegment

from app.logging.setup import get_logger

log = get_logger("converter")


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
