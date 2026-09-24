"""Opt-in Stem Record — long-form mux off the capture and bus threads.

The ``stem-record`` thread samples the ClipBuffer LIVE slot, decodes JPEGs and
writes a raw AVI at a fixed fps paced by each frame's ``clock_ns``, so video
time matches session wall time (chapters and segments line up). Short capture
gaps repeat the current frame; gaps longer than ``GAP_DARK_S`` are written as
black frames — a stall shows as dark, never as a frozen picture. ``stop()``
transcodes to browser-safe H.264 via ffmpeg (keeps the raw AVI if ffmpeg is
missing) and writes the chapters sidecar against the real file.
"""

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
DEFAULT_FPS = 30.0
GAP_DARK_S = 0.5
JOIN_TIMEOUT_S = 10.0


class StemRecord:
    def __init__(
        self,
        bus: Any | None = None,
        *,
        out_dir: str = "clips",
        session_head_ns: int | None = None,
        fps: float = DEFAULT_FPS,
    ) -> None:
        self.bus = bus
        self.out_dir = Path(out_dir)
        self._session_head_ns = session_head_ns
        self.fps = float(max(1.0, fps))
        self._q: queue.Queue[tuple[int, bytes]] = queue.Queue(maxsize=QUEUE_MAX)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._active = False
        self._dropped = 0
        self._written = 0
        self._frames_out = 0
        self._dark_frames = 0
        self._late = 0
        self._path: Path | None = None
        self._raw_path: Path | None = None
        self._final_path: Path | None = None
        self._h264: bool | None = None
        self._writer: Any = None
        self._size: tuple[int, int] | None = None
        self._start_ns: int | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self._path = self.out_dir / f"stem_{stamp}.mp4"
        self._raw_path = self._path.with_name(self._path.stem + "_raw.avi")
        self._final_path = None
        self._h264 = None
        self._start_ns = clock_ns()
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
            t.join(timeout=JOIN_TIMEOUT_S)
            if t.is_alive():
                log.warning("Stem Record writer still busy; skipping finalize")
                self._active = False
                return
        self._thread = None
        self._active = False
        end_ns = clock_ns()
        start_ns = self._start_ns if self._start_ns is not None else end_ns
        duration_s = max(1.0, (end_ns - start_ns) / 1e9)
        path = self._finalize(duration_s)
        if path is not None:
            try:
                from qoresence.vision.clip_chapters import chapters_after_export

                chapters_after_export(
                    path,
                    duration_s=duration_s,
                    window_start_ns=start_ns,
                    window_end_ns=end_ns,
                )
            except Exception as e:
                log.debug("stem chapters skipped: %s", e)
        self._emit(
            {
                "active": False,
                "path": str(path) if path else "",
                "frames": self._frames_out,
                "h264": bool(self._h264),
            }
        )

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
            final = self._final_path
            return {
                "active": self._active,
                "path": str(final or self._path) if (final or self._path) else None,
                "written": self._written,
                "frames_out": self._frames_out,
                "dark_frames": self._dark_frames,
                "late": self._late,
                "dropped": self._dropped,
                "queued": self._q.qsize(),
                "fps": self.fps,
                "h264": self._h264,
            }

    def _loop(self) -> None:
        """Pull JPEG snapshots from ClipBuffer LIVE slot; mux off-thread."""
        last_seq: int | None = None
        try:
            while True:
                stopping = self._stop.is_set()
                if not stopping:
                    try:
                        from qoresence.vision.clip_buffer import get_latest_frame

                        latest = get_latest_frame()
                        if latest and latest[0] and latest[1] != last_seq:
                            last_seq = latest[1]
                            self.enqueue_jpeg(latest[0])
                    except Exception:
                        pass
                try:
                    ts, jpeg = self._q.get(timeout=0.01)
                except queue.Empty:
                    if stopping:
                        break
                    continue
                with self._lock:
                    self._written += 1
                try:
                    self._write_frame(ts, jpeg)
                except Exception as e:
                    log.debug("stem frame write skipped: %s", e)
        finally:
            self._release_writer()

    def _write_frame(self, ts_ns: int, jpeg: bytes) -> None:
        """Decode one JPEG and pace it onto the fixed-fps timeline by ``ts_ns``."""
        import cv2
        import numpy as np

        img = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return
        if self._writer is None and not self._open_writer(img.shape[1], img.shape[0]):
            return
        w, h = self._size or (img.shape[1], img.shape[0])
        if img.shape[1] != w or img.shape[0] != h:
            img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
        start = self._start_ns if self._start_ns is not None else ts_ns
        target = int(max(0, ts_ns - start) * self.fps / 1e9)
        if self._frames_out and target < self._frames_out:
            with self._lock:
                self._late += 1
            return
        gap = target - self._frames_out
        dark = 0
        if self._frames_out and gap / self.fps > GAP_DARK_S:
            black = np.zeros((h, w, 3), dtype=np.uint8)
            for _ in range(gap):
                self._writer.write(black)
            dark, gap = gap, 0
        for _ in range(gap + 1):
            self._writer.write(img)
        with self._lock:
            self._frames_out += dark + gap + 1
            self._dark_frames += dark

    def _open_writer(self, w: int, h: int) -> bool:
        import cv2

        raw = self._raw_path
        if raw is None:
            return False
        for code in ("XVID", "MJPG"):
            writer = cv2.VideoWriter(str(raw), cv2.VideoWriter_fourcc(*code), self.fps, (w, h))
            if writer.isOpened():
                self._writer = writer
                self._size = (w, h)
                return True
            writer.release()
        log.error("Stem Record: VideoWriter failed to open %s", raw)
        return False

    def _release_writer(self) -> None:
        writer, self._writer = self._writer, None
        if writer is not None:
            try:
                writer.release()
            except Exception:
                pass

    def _finalize(self, duration_s: float) -> Path | None:
        """Raw AVI → H.264 MP4. Keeps the AVI when ffmpeg is unavailable."""
        raw, path = self._raw_path, self._path
        if raw is None or path is None or self._frames_out < 2 or not raw.exists():
            return None
        from qoresence.vision.clip_buffer import HdmiClipBuffer

        ok = HdmiClipBuffer._ffmpeg_h264(
            raw, path, self.fps, timeout_s=max(120.0, duration_s * 2.0)
        )
        if ok and path.exists():
            raw.unlink(missing_ok=True)
            final = path
        else:
            log.warning("ffmpeg H.264 unavailable — Stem Record kept %s", raw)
            final = raw
        with self._lock:
            self._final_path = final
            self._h264 = bool(ok)
        log.info(
            "Stem Record saved: %s (%d frames, %d dark, %.1fs, h264=%s)",
            final,
            self._frames_out,
            self._dark_frames,
            duration_s,
            ok,
        )
        return final

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
