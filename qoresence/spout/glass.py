"""Spout Glass runtime — FrameHub subscribe → Spout2, never blocks grab."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from qoresence.spout.sender import DEFAULT_SENDER_NAME, SpoutSender, create_sender

log = logging.getLogger(__name__)

_glass: SpoutGlass | None = None
_glass_lock = threading.Lock()


class SpoutGlass:
    """Latest-frame Spout publisher. Drop under load. Default OFF at CLI."""

    def __init__(
        self,
        sender_name: str = DEFAULT_SENDER_NAME,
        target_hz: float = 60.0,
        sender: SpoutSender | None = None,
    ) -> None:
        self._name = sender_name or DEFAULT_SENDER_NAME
        self._hz = max(1.0, float(target_hz or 60.0))
        self._sender = sender
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._enabled = False
        self._published = 0
        self._drops = 0
        self._empty = 0
        self._errors = 0
        self._last_seq = 0
        self._last_clock_ns = 0
        self._last_send_mono = 0.0
        self._backend = "unstarted"

    def start(self) -> threading.Thread:
        if self._thread is not None and self._thread.is_alive():
            return self._thread
        if self._sender is None:
            self._sender = create_sender(self._name)
        self._backend = getattr(self._sender, "backend", "unknown")
        self._enabled = True
        self._stop.clear()
        t = threading.Thread(target=self._run, name="spout-glass", daemon=True)
        self._thread = t
        t.start()
        log.info(
            "Spout Glass on (FrameHub → %s name=%s backend=%s; no DShow)",
            self._name,
            self._name,
            self._backend,
        )
        return t

    def stop(self) -> None:
        self._stop.set()
        self._enabled = False
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=2.0)
        if self._sender is not None:
            try:
                self._sender.close()
            except Exception as e:
                log.debug("Spout sender close: %s", e)
        self._thread = None

    def health(self) -> dict[str, Any]:
        age = None
        if self._last_send_mono:
            age = round(time.monotonic() - self._last_send_mono, 3)
        return {
            "enabled": bool(self._enabled),
            "sender_name": self._name,
            "backend": self._backend,
            "target_hz": self._hz,
            "published": int(self._published),
            "drops": int(self._drops),
            "empty_polls": int(self._empty),
            "errors": int(self._errors),
            "last_frame_seq": int(self._last_seq),
            "last_clock_ns": int(self._last_clock_ns),
            "last_send_age_s": age,
            "thread_alive": bool(self._thread is not None and self._thread.is_alive()),
        }

    def _run(self) -> None:
        period = 1.0 / self._hz
        assert self._sender is not None
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                self._tick()
            except Exception as e:
                self._errors += 1
                log.debug("Spout Glass tick: %s", e)
            elapsed = time.monotonic() - t0
            sleep_s = period - elapsed
            if sleep_s > 0:
                self._stop.wait(sleep_s)
            else:
                # Behind schedule — drop rather than catch up under lock
                self._drops += 1

    def _tick(self) -> None:
        # Latest-frame only; copy happens inside get_latest_meta. Never streamer lock.
        from qoresence.monitor.frame_hub import get_frame_hub

        frame, seq, _age = get_frame_hub().get_latest_meta()
        if frame is None:
            self._empty += 1
            return
        if seq == self._last_seq and self._last_seq != 0:
            # Same frame — skip send (not a drop of new work)
            return
        stamp = get_frame_hub().get_latest_stamp()
        ok = self._sender.send(frame) if self._sender is not None else False
        if ok:
            self._published += 1
            self._last_seq = int(seq)
            self._last_clock_ns = int(stamp.get("clock_ns") or 0)
            self._last_send_mono = time.monotonic()
        else:
            self._errors += 1


def get_spout_glass() -> SpoutGlass | None:
    with _glass_lock:
        return _glass


def set_spout_glass(glass: SpoutGlass | None) -> None:
    global _glass
    with _glass_lock:
        _glass = glass


def spout_health() -> dict[str, Any]:
    g = get_spout_glass()
    if g is None:
        return {
            "enabled": False,
            "sender_name": DEFAULT_SENDER_NAME,
            "backend": "off",
            "published": 0,
            "drops": 0,
        }
    return g.health()
