"""Stem Audio lobe — capture-card audio on clock_ns. Never a laptop mic.

Bus payload is levels / onset only — never raw PCM on the bus.
"""

from __future__ import annotations

import logging
import math
import struct
import threading
import time
from collections import deque
from typing import Any

from qoresence.core.types import EventType, SourceLobe, clock_ns
from qoresence.stem.resolve import list_audio_devices, resolve_audio_device

log = logging.getLogger(__name__)

ONSET_RMS = 0.12
RING_S = 45.0


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

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            age = (clock_ns() - self._last_ns) / 1e9 if self._last_ns else None
            return {
                "enabled": self._device is not None,
                "device": self._device[1] if self._device else None,
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
            with sd.InputStream(device=idx, channels=1, samplerate=48000, blocksize=2048) as stream:
                while not self._stop.is_set():
                    data, _overflowed = stream.read(2048)
                    rms = _rms(data)
                    now = clock_ns()
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
                    time.sleep(0)
        except Exception as e:
            log.warning("Stem Audio stream failed (card audio only, no mic fallback): %s", e)


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
