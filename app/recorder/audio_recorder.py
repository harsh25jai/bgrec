"""Microphone recording in timed chunks with reconnect handling."""

from __future__ import annotations

import queue
import threading
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np
import sounddevice as sd

from app.config.settings import RecordingConfig
from app.logging.setup import get_logger
from app.recorder.converter import wav_to_compressed

log = get_logger("recorder")


def list_input_devices() -> list[dict]:
    devices = []
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            devices.append({"index": i, "name": dev["name"], "channels": dev["max_input_channels"]})
    return devices


def _resolve_device(device: str | None) -> int | None:
    if device is None or device.strip() == "":
        return None
    if device.isdigit():
        return int(device)
    for i, dev in enumerate(sd.query_devices()):
        if device.lower() in dev["name"].lower() and dev["max_input_channels"] > 0:
            return i
    raise ValueError(f"Recording device not found: {device}")


def _rms_db(frame: np.ndarray) -> float:
    if frame.size == 0:
        return -100.0
    rms = np.sqrt(np.mean(frame.astype(np.float64) ** 2))
    if rms < 1e-10:
        return -100.0
    return 20 * np.log10(rms)


class ChunkRecorder:
    """Records microphone audio in fixed-duration chunks on a background thread."""

    def __init__(
        self,
        config: RecordingConfig,
        output_dir: Path,
        on_chunk: Callable[[Path], None] | None = None,
    ) -> None:
        self.config = config
        self.output_dir = output_dir
        self.on_chunk = on_chunk
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._device_index: int | None = None
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, name="chunk-recorder", daemon=True)
        self._thread.start()
        log.info("Recorder started (chunk={}s)", self.config.chunk_duration_seconds)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.config.chunk_duration_seconds + 10)
        log.info("Recorder stopped")

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    def _run_loop(self) -> None:
        reconnect_delay = 2.0
        while not self._stop.is_set():
            try:
                self._device_index = _resolve_device(self.config.device)
                self._record_session()
            except sd.PortAudioError as exc:
                log.error("Audio device error: {} — retrying in {}s", exc, reconnect_delay)
                time.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 1.5, 30.0)
            except Exception as exc:
                log.exception("Recorder loop error: {}", exc)
                time.sleep(reconnect_delay)

    def _record_session(self) -> None:
        chunk_samples = int(self.config.sample_rate * self.config.chunk_duration_seconds)
        blocksize = int(self.config.sample_rate * 0.1)  # 100 ms blocks
        q: queue.Queue[np.ndarray] = queue.Queue()
        silence_start: float | None = None

        def callback(indata, frames, time_info, status):  # noqa: ARG001
            if status:
                log.warning("PortAudio status: {}", status)
            q.put(indata.copy())

        stream_kwargs = dict(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype="int16",
            callback=callback,
            blocksize=blocksize,
        )
        if self._device_index is not None:
            stream_kwargs["device"] = self._device_index

        with sd.InputStream(**stream_kwargs):
            log.info("Audio stream open (device={})", self._device_index)
            buffer: list[np.ndarray] = []
            collected = 0

            while not self._stop.is_set():
                try:
                    block = q.get(timeout=1.0)
                except queue.Empty:
                    continue

                flat = block.reshape(-1)
                buffer.append(block)
                collected += len(flat)

                if self.config.silence_detection:
                    db = _rms_db(flat.astype(np.float32) / 32768.0)
                    if db < self.config.silence_threshold_db:
                        if silence_start is None:
                            silence_start = time.monotonic()
                        elif (
                            time.monotonic() - silence_start
                            >= self.config.silence_min_duration_seconds
                            and collected > 0
                        ):
                            log.debug("Silence detected; finalizing early chunk")
                            self._finalize_chunk(buffer, collected)
                            buffer, collected = [], 0
                            silence_start = None
                            continue
                    else:
                        silence_start = None

                if collected >= chunk_samples:
                    self._finalize_chunk(buffer, chunk_samples)
                    # Keep overflow for next chunk
                    flat_all = np.concatenate([b.reshape(-1) for b in buffer])
                    overflow = flat_all[chunk_samples:]
                    buffer = [overflow.reshape(-1, self.config.channels)] if len(overflow) else []
                    collected = len(overflow)

        # Flush partial buffer on shutdown
        if buffer and collected > 0:
            self._finalize_chunk(buffer, collected)

    def _finalize_chunk(self, buffer: list[np.ndarray], sample_count: int) -> None:
        if not buffer:
            return
        flat = np.concatenate([b.reshape(-1) for b in buffer])[:sample_count]
        if len(flat) == 0:
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        wav_path = self.output_dir / f"rec_{ts}.wav"
        frames = flat.reshape(-1, self.config.channels)

        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(self.config.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.config.sample_rate)
            wf.writeframes(frames.astype(np.int16).tobytes())

        try:
            out_path = wav_to_compressed(
                wav_path,
                output_format=self.config.output_format,
                mp3_bitrate=self.config.mp3_bitrate,
            )
        except Exception as exc:
            log.error("Conversion failed for {}: {}", wav_path.name, exc)
            out_path = wav_path

        log.info("Chunk saved: {}", out_path.name)
        if self.on_chunk:
            self.on_chunk(out_path)
