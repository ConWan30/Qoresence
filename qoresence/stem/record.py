"""Opt-in Stem Record — long-form mux off the capture and bus threads."""

from __future__ import annotations

import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any

from qoresence.core.types import EventType, SourceLobe, clock_ns

log = logging.getLogger(__name__)

QUEUE_MAX = 120  # drop-oldest ~2s at 60 if mux lags


class StemRecord:
    def __init__(
        self,
        bus: Any | None = None,
        *,
        out_dir: str = "clips",
        session_head_ns: int | None = None,
    ) -> None:
        self.bus = bus
        self.out_dir = Path(out_dir)
        self._session_head_ns = session_head_ns
        self._q: queue.Queue[tuple[int, bytes]] = queue.Queue(maxsize=QUEUE_MAX)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._active = False
        self._dropped = 0
        self._written = 0
        self._path: Path | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self._path = self.out_dir / f"stem_{stamp}.mp4"
        self._stop.clear()
        self._active = True
        self._thread = threading.Thread(target=self._loop, name="stem-record", daemon=True)
        self._thread.start()
        self._emit({"active": True, "path": str(self._path)})
        log.info("Stem Record on %s (drop-oldest queue=%d)", self._path, QUEUE_MAX)

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t is not None:
            t.join(timeout=3.0)
        self._thread = None
        self._active = False
        path = self._path
        if path is not None:
            try:
                from qoresence.vision.clip_chapters import chapters_after_export

                chapters_after_export(path, duration_s=max(1.0, self._written / 30.0))
            except Exception as e:
                log.debug("stem chapters skipped: %s", e)
        self._emit({"active": False, "path": str(path) if path else "", "frames": self._written})

    def enqueue_jpeg(self, jpeg: bytes, ts_ns: int | None = None) -> None:
        """Called from a worker — never from a bus subscriber that might block."""
        if not self._active or not jpeg:
            return
        item = (int(ts_ns or clock_ns()), jpeg)
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

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active": self._active,
                "path": str(self._path) if self._path else None,
                "written": self._written,
                "dropped": self._dropped,
                "queued": self._q.qsize(),
            }

    def _loop(self) -> None:
        """Pull JPEG snapshots from ClipBuffer LIVE slot; mux off-thread."""
        last_seq = -1
        while not self._stop.is_set():
            try:
                from qoresence.vision.clip_buffer import get_clip_buffer, get_latest_jpeg

                buf = get_clip_buffer()
                jpg = get_latest_jpeg()
                seq = getattr(buf, "_live_seq", None)
                if jpg and seq != last_seq:
                    last_seq = seq
                    self.enqueue_jpeg(jpg)
            except Exception:
                pass
            try:
                _ts, _jpeg = self._q.get(timeout=0.05)
            except queue.Empty:
                continue
            with self._lock:
                self._written += 1
            time.sleep(0)

    def _emit(self, payload: dict[str, Any]) -> None:
        if self.bus is None:
            return
        try:
            self.bus.emit_raw(
                source_lobe=SourceLobe.STEM,
                event_type=EventType.STEM_RECORD.value,
                payload=payload,
                session_head_ns=self._session_head_ns,
            )
        except Exception as e:
            log.debug("stem_record emit skipped: %s", e)
