"""Stem audio track — capture-card PCM to a clock-aligned WAV for the Stem MP4.

Blocks arrive from the ``stem-audio`` stream thread with the ``clock_ns`` at
which the read returned. The ``stem-audio-writer`` thread places each block on
the session timeline (sample 0 = Stem Record ``start_ns``):

- behind the clock by more than ``DRIFT_TOL_S`` → write digital silence first
  (a dropout sounds silent, never stretched or repeated)
- ahead of the clock by more than ``DRIFT_TOL_S`` → trim the block head

Raw PCM never touches the bus. The stream thread only enqueues (drop-oldest).
"""

from __future__ import annotations

import logging
import queue
import threading
import wave
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DRIFT_TOL_S = 0.040
QUEUE_BLOCKS = 256  # ~11 s of 2048-sample blocks at 48 kHz


def to_int16(data: Any) -> Any:
    """Float [-1, 1] (sounddevice default) or int16 → mono int16 ndarray."""
    import numpy as np

    arr = np.asarray(data)
    if arr.ndim > 1:
        arr = arr.mean(axis=1) if arr.dtype.kind == "f" else arr[:, 0]
    if arr.dtype.kind == "f":
        arr = np.clip(arr, -1.0, 1.0) * 32767.0
    return arr.astype(np.int16).ravel()


class StemAudioTrack:
    def __init__(self, path: str | Path, *, start_ns: int, samplerate: int) -> None:
        self.path = Path(path)
        self.start_ns = int(start_ns)
        self.samplerate = int(samplerate)
        self._tol = int(DRIFT_TOL_S * self.samplerate)
        self._q: queue.Queue[tuple[int, Any] | None] = queue.Queue(maxsize=QUEUE_BLOCKS)
        self._lock = threading.Lock()
        self._samples = 0
        self._blocks = 0
        self._silence = 0
        self._trimmed = 0
        self._dropped = 0
        self._wav: wave.Wave_write | None = None
        self._thread: threading.Thread | None = None

    def open(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            wav = wave.open(str(self.path), "wb")
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.samplerate)
        except Exception as e:
            log.warning("Stem audio track not opened (%s): %s", self.path, e)
            return False
        self._wav = wav
        self._thread = threading.Thread(target=self._run, name="stem-audio-writer", daemon=True)
        self._thread.start()
        return True

    def feed(self, ts_ns: int, pcm: Any) -> None:
        """Stream-thread hot path: enqueue only, drop-oldest when full."""
        item = (int(ts_ns), pcm)
        try:
            self._q.put_nowait(item)
        except queue.Full:
            try:
                self._q.get_nowait()
            except queue.Empty:
                pass
            with self._lock:
                self._dropped += 1
            try:
                self._q.put_nowait(item)
            except queue.Full:
                pass

    def close(self, *, pad_to_s: float | None = None) -> Path | None:
        """Drain, pad with silence to ``pad_to_s``, close. None if nothing was captured."""
        t = self._thread
        if t is not None:
            while True:
                try:
                    self._q.put(None, timeout=0.5)
                    break
                except queue.Full:
                    if not t.is_alive():
                        break
            t.join(timeout=5.0)
        self._thread = None
        wav, self._wav = self._wav, None
        if wav is None:
            return None
        blocks = self._blocks
        try:
            if blocks and pad_to_s is not None:
                self._write_silence(wav, int(pad_to_s * self.samplerate) - self._samples)
        finally:
            wav.close()
        if not blocks:
            self.path.unlink(missing_ok=True)
            return None
        return self.path

    def stats(self) -> dict[str, Any]:
        sr = float(self.samplerate)
        with self._lock:
            return {
                "samplerate": self.samplerate,
                "blocks": self._blocks,
                "samples": self._samples,
                "silence_ms": round(self._silence * 1000.0 / sr, 1),
                "trimmed_ms": round(self._trimmed * 1000.0 / sr, 1),
                "dropped_blocks": self._dropped,
            }

    def _run(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                return
            wav = self._wav
            if wav is None:
                return
            try:
                self._place(wav, *item)
            except Exception as e:
                log.debug("stem audio block skipped: %s", e)

    def _place(self, wav: wave.Wave_write, ts_ns: int, pcm: Any) -> None:
        block = to_int16(pcm)
        n = int(block.size)
        if n == 0:
            return
        block_start = ts_ns - int(n * 1e9 / self.samplerate)
        target = int((block_start - self.start_ns) * self.samplerate / 1e9)
        diff = target - self._samples
        trimmed = 0
        if diff > self._tol or (self._blocks == 0 and diff > 0):
            self._write_silence(wav, diff)
        elif diff < -self._tol or (self._blocks == 0 and diff < 0):
            trimmed = min(n, -diff)
            block = block[trimmed:]
        if block.size:
            wav.writeframes(block.tobytes())
        with self._lock:
            self._blocks += 1
            self._samples += int(block.size)
            self._trimmed += trimmed

    def _write_silence(self, wav: wave.Wave_write, n: int) -> None:
        if n <= 0:
            return
        chunk = b"\x00\x00" * min(n, self.samplerate)
        left = n
        while left > 0:
            k = min(left, self.samplerate)
            wav.writeframes(chunk[: k * 2])
            left -= k
        with self._lock:
            self._samples += n
            self._silence += n
