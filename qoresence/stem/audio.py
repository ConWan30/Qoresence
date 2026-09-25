"""Stem Audio lobe — capture-card audio on clock_ns. Never a laptop mic.

Bus payload is levels / onset only — never raw PCM on the bus. While Stem
Record is on, PCM blocks are also handed to a ``StemAudioTrack`` (enqueue
only) so the Stem MP4 carries card audio on the same clock as its video.
"""

from __future__ import annotations

import logging
import math
import struct
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from qoresence.core.types import EventType, SourceLobe, clock_ns
from qoresence.stem.audio_track import StemAudioTrack
from qoresence.stem.resolve import list_audio_devices, resolve_audio_device

log = logging.getLogger(__name__)

ONSET_RMS = 0.12
RING_S = 45.0
DEFAULT_SAMPLERATE = 48000
BLOCKSIZE = 2048


class StemAudio:
    def __init__(
        self,
        bus: Any | None = None,
        *,
        session_head_ns: int | None = None,
        prefer_name: str | None = None,
    ) -> None:
        self.bus = bus
        self._session_head_ns = session_head_ns
        self._prefer_name = prefer_name
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._device: tuple[int, str] | None = None
        self._last_rms = 0.0
        self._last_onset = False
        self._last_ns = 0
        self._pcm: deque[tuple[int, float]] = deque()  # (clock_ns, rms)
        self.samplerate = DEFAULT_SAMPLERATE
        self._track: StemAudioTrack | None = None
        self._track_stats: dict[str, Any] | None = None

    def start(self) -> None:
        devices = list_audio_devices()
        self._device = resolve_audio_device(devices, prefer_name=self._prefer_name)
        if self._device is None:
            log.info(
                "Stem Audio: no capture-card audio (HDMI unplugged?). "
                "Laptop mic stays closed."
            )
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="stem-audio", daemon=True)
        self._thread.start()
        log.info("Stem Audio on device %s (%s)", self._device[0], self._device[1])

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t is not None:
            t.join(timeout=1.5)
        self._thread = None

    def start_capture(self, path: str | Path, start_ns: int) -> bool:
        """Begin writing card PCM to ``path``; sample 0 is ``start_ns``."""
        if self._device is None or self._thread is None:
            return False
        track = StemAudioTrack(path, start_ns=start_ns, samplerate=self.samplerate)
        if not track.open():
            return False
        with self._lock:
            old, self._track = self._track, track
            self._track_stats = None
        if old is not None:
            old.close()
        return True

    def stop_capture(self, *, pad_to_s: float | None = None) -> Path | None:
        """Stop the track; pad to the video length. None when nothing was captured."""
        with self._lock:
            track, self._track = self._track, None
        if track is None:
            return None
        path = track.close(pad_to_s=pad_to_s)
        with self._lock:
            self._track_stats = track.stats()
        return path

    def capture_stats(self) -> dict[str, Any] | None:
        with self._lock:
            track = self._track
            last = self._track_stats
        return track.stats() if track is not None else last

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            age = (clock_ns() - self._last_ns) / 1e9 if self._last_ns else None
            return {
                "enabled": self._device is not None,
                "device": self._device[1] if self._device else None,
                "samplerate": self.samplerate,
                "capturing": self._track is not None,
                "rms": round(self._last_rms, 4),
                "onset": self._last_onset,
                "age_s": None if age is None else round(age, 3),
            }

    def overlap_rms(self, start_ns: int, end_ns: int) -> list[tuple[int, float]]:
        with self._lock:
            return [(t, r) for t, r in self._pcm if start_ns <= t <= end_ns]

    def _loop(self) -> None:
        """Pull samples if sounddevice is present; otherwise idle after resolve."""
        try:
            import sounddevice as sd  # type: ignore[import-untyped]
        except Exception:
            log.info("Stem Audio: sounddevice missing — resolve-only (no mic open)")
            return
        if self._device is None:
            return
        idx, _name = self._device
        try:
            rate = int(sd.query_devices(idx).get("default_samplerate") or DEFAULT_SAMPLERATE)
        except Exception:
            rate = DEFAULT_SAMPLERATE
        self.samplerate = rate if rate > 0 else DEFAULT_SAMPLERATE
        try:
            with sd.InputStream(
                device=idx, channels=1, samplerate=self.samplerate, blocksize=BLOCKSIZE
            ) as stream:
                while not self._stop.is_set():
                    data, _overflowed = stream.read(BLOCKSIZE)
                    self._on_block(data, clock_ns())
                    time.sleep(0)
        except Exception as e:
            log.warning("Stem Audio stream failed (card audio only, no mic fallback): %s", e)

    def _on_block(self, data: Any, now: int) -> None:
        """One stream block: levels under lock; PCM tap + onset emit after release."""
        rms = _rms(data)
        onset = rms >= ONSET_RMS
        payload = None
        with self._lock:
            self._last_rms = rms
            self._last_onset = onset
            self._last_ns = now
            self._pcm.append((now, rms))
            cutoff = now - int(RING_S * 1e9)
            while self._pcm and self._pcm[0][0] < cutoff:
                self._pcm.popleft()
            if onset:
                payload = {"rms": round(rms, 4), "onset": True}
            track = self._track
        if track is not None:
            track.feed(now, data)
        if payload is not None and self.bus is not None:
            try:
                self.bus.emit_raw(
                    source_lobe=SourceLobe.STEM,
                    event_type=EventType.STEM_AUDIO.value,
                    payload=payload,
                    clock_ns_override=now,
                    session_head_ns=self._session_head_ns,
                )
            except Exception as e:
                log.debug("stem_audio emit skipped: %s", e)


def _rms(data: Any) -> float:
    try:
        import numpy as np

        arr = np.asarray(data, dtype=float).ravel()
        if arr.size == 0:
            return 0.0
        return float(math.sqrt(float(np.mean(arr * arr))))
    except Exception:
        if isinstance(data, (bytes, bytearray)):
            if len(data) < 4:
                return 0.0
            n = len(data) // 2
            acc = 0.0
            for i in range(n):
                v = struct.unpack_from("<h", data, i * 2)[0] / 32768.0
                acc += v * v
            return math.sqrt(acc / n)
        return 0.0
