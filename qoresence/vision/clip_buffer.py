"""Rolling HDMI clip buffer — true local capture from streamer frames.

Keeps the last N seconds of downscaled JPEG frames at a capped FPS so memory
stays bounded, then encodes MP4 on demand for Foundry / ClutchBot clip actions.

This is *not* Twitch Helix. Source is the UVC/DShow capture card (PS5 HDMI).
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

log = logging.getLogger(__name__)

DEFAULT_SECONDS = 30.0
# Half-sample of 60 Hz PS5 HDMI for smooth LIVE + bounded RAM (not full-rate JPEG).
# Full 60 via get_clip_buffer(target_fps=60) or GET /video?fps=60.
DEFAULT_FPS = 30.0
DEFAULT_MAX_WIDTH = 960
DEFAULT_JPEG_QUALITY = 75  # slightly lower to offset 30 fps frame count
DEFAULT_OUT_DIR = Path("clips")


@dataclass
class ClipExportResult:
    path: str
    frames: int
    duration_s: float
    width: int
    height: int
    fps: float
    size_bytes: int
    source: str = "hdmi_local"


class HdmiClipBuffer:
    """Thread-safe ring of recent capture frames for local clip export."""

    def __init__(
        self,
        seconds: float = DEFAULT_SECONDS,
        target_fps: float = DEFAULT_FPS,
        max_width: int = DEFAULT_MAX_WIDTH,
        jpeg_quality: int = DEFAULT_JPEG_QUALITY,
        out_dir: str | Path = DEFAULT_OUT_DIR,
    ):
        self.seconds = float(seconds)
        self.target_fps = float(target_fps)
        self.max_width = int(max_width)
        self.jpeg_quality = int(jpeg_quality)
        self.out_dir = Path(out_dir)
        self._interval = 1.0 / max(self.target_fps, 1.0)
        self._maxlen = max(1, int(self.seconds * self.target_fps) + 2)
        # (ts, jpeg_bytes, w, h, seq)
        self._frames: deque[tuple[float, bytes, int, int, int]] = deque(maxlen=self._maxlen)
        self._lock = threading.Lock()
        self._last_push = 0.0
        self._pushes = 0
        self._skipped = 0
        self._seq = 0
        self._enabled = True

    def enable(self, on: bool = True) -> None:
        self._enabled = bool(on)

    def push(self, frame: np.ndarray | None) -> None:
        """Ingest a BGR frame from the streamer (throttled + resized + JPEG)."""
        if not self._enabled or frame is None:
            return
        try:
            if not hasattr(frame, "shape") or len(frame.shape) < 2:
                return
            now = time.monotonic()
            if now - self._last_push < self._interval:
                self._skipped += 1
                return
            self._last_push = now

            h, w = int(frame.shape[0]), int(frame.shape[1])
            if self.max_width > 0 and w > self.max_width:
                scale = self.max_width / float(w)
                nh = max(1, int(h * scale))
                small = cv2.resize(frame, (self.max_width, nh), interpolation=cv2.INTER_AREA)
            else:
                small = frame
            sh, sw = int(small.shape[0]), int(small.shape[1])
            # even dims for some codecs
            if sw % 2:
                small = small[:, : sw - 1]
                sw -= 1
            if sh % 2:
                small = small[: sh - 1, :]
                sh -= 1
            ok, buf = cv2.imencode(
                ".jpg", small, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
            )
            if not ok:
                return
            with self._lock:
                self._seq += 1
                self._frames.append((now, buf.tobytes(), sw, sh, self._seq))
                self._pushes += 1
        except Exception as e:
            log.debug("ClipBuffer push failed: %s", e)

    def latest_jpeg(self) -> bytes | None:
        """Return newest JPEG bytes in the ring (no re-encode). Empty → None."""
        with self._lock:
            if not self._frames:
                return None
            return self._frames[-1][1]

    def latest_frame(self) -> tuple[bytes, int] | None:
        """Return (jpeg_bytes, seq) for newest frame. Empty → None."""
        with self._lock:
            if not self._frames:
                return None
            _ts, jpg, _w, _h, seq = self._frames[-1]
            return (jpg, seq)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            n = len(self._frames)
            now = time.monotonic()
            if n >= 2:
                dur = self._frames[-1][0] - self._frames[0][0]
            else:
                dur = 0.0
            w = self._frames[-1][2] if n else 0
            h = self._frames[-1][3] if n else 0
            age_s = (now - self._frames[-1][0]) if n else None
            seq = self._frames[-1][4] if n else 0
            return {
                "enabled": self._enabled,
                "frames": n,
                "capacity": self._maxlen,
                "duration_s": round(dur, 2),
                "target_fps": self.target_fps,
                "width": w,
                "height": h,
                "pushes": self._pushes,
                "skipped": self._skipped,
                "out_dir": str(self.out_dir.resolve()),
                "has_frame": n > 0,
                "age_s": None if age_s is None else round(float(age_s), 3),
                "seq": int(seq),
            }

    def export(
        self,
        path: str | Path | None = None,
        seconds: float | None = None,
    ) -> ClipExportResult | None:
        """Encode buffered HDMI frames to an MP4 file."""
        seconds = float(seconds) if seconds is not None else self.seconds
        with self._lock:
            if not self._frames:
                log.warning("ClipBuffer export: no frames yet (is streamer running?)")
                return None
            t_end = self._frames[-1][0]
            t_start = t_end - max(0.5, seconds)
            selected = [f for f in self._frames if f[0] >= t_start]
            if len(selected) < 2:
                selected = list(self._frames)
            snapshot = list(selected)

        if len(snapshot) < 2:
            log.warning("ClipBuffer export: need >=2 frames, have %d", len(snapshot))
            return None

        w = snapshot[0][2]
        h = snapshot[0][3]
        # force consistent size
        for _ts, _jpg, fw, fh in snapshot:
            w, h = fw, fh
            break

        span = snapshot[-1][0] - snapshot[0][0]
        fps = (len(snapshot) - 1) / span if span > 0.05 else self.target_fps
        # Allow full PS5-rate encode when ring was filled at 60
        fps = float(min(60.0, max(5.0, fps)))

        self.out_dir.mkdir(parents=True, exist_ok=True)
        if path is None:
            stamp = time.strftime("%Y%m%d_%H%M%S")
            path = self.out_dir / f"hdmi_clip_{stamp}.mp4"
        else:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)

        # OpenCV mp4v/FMP4 is NOT playable in Chrome/Edge <video>. Write a raw
        # intermediate, then remux/transcode to H.264 (yuv420p) via ffmpeg when
        # available so Ghost Theater can play with one click.
        path = Path(path)
        if path.suffix.lower() not in {".mp4", ".avi"}:
            path = path.with_suffix(".mp4")
        raw_path = path.with_name(path.stem + "_raw.avi")

        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        writer = cv2.VideoWriter(str(raw_path), fourcc, fps, (w, h))
        if not writer.isOpened():
            fourcc = cv2.VideoWriter_fourcc(*"MJPG")
            raw_path = path.with_name(path.stem + "_raw.avi")
            writer = cv2.VideoWriter(str(raw_path), fourcc, fps, (w, h))
        if not writer.isOpened():
            log.error("ClipBuffer: VideoWriter failed to open %s", raw_path)
            return None

        written = 0
        try:
            for _ts, jpg, fw, fh in snapshot:
                arr = np.frombuffer(jpg, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is None:
                    continue
                if img.shape[1] != w or img.shape[0] != h:
                    img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
                writer.write(img)
                written += 1
        finally:
            writer.release()

        if written < 2 or not raw_path.exists():
            log.error("ClipBuffer export produced no usable file")
            return None

        final_path = path.with_suffix(".mp4")
        ok_h264 = self._ffmpeg_h264(raw_path, final_path, fps)
        try:
            if raw_path.exists() and raw_path != final_path:
                raw_path.unlink(missing_ok=True)  # type: ignore[arg-type]
        except Exception:
            pass

        if not ok_h264 or not final_path.exists():
            # Last resort: keep raw as .avi (may not play in-browser)
            final_path = raw_path if raw_path.exists() else final_path
            log.warning(
                "ffmpeg H.264 unavailable — browser may not play %s (install ffmpeg)",
                final_path,
            )

        size = final_path.stat().st_size if final_path.exists() else 0
        dur = written / fps if fps > 0 else 0.0
        log.info(
            "HDMI clip saved: %s (%d frames, %.1fs, %dx%d, %d KB, h264=%s)",
            final_path,
            written,
            dur,
            w,
            h,
            size // 1024,
            ok_h264,
        )
        return ClipExportResult(
            path=str(final_path.resolve()),
            frames=written,
            duration_s=round(dur, 2),
            width=w,
            height=h,
            fps=round(fps, 2),
            size_bytes=size,
            source="hdmi_local",
        )

    @staticmethod
    def _ffmpeg_h264(src: Path, dst: Path, fps: float) -> bool:
        """Transcode to browser-safe H.264 MP4 (+faststart for progressive play)."""
        import shutil
        import subprocess

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return False
        dst.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-an",
            str(dst),
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                log.warning("ffmpeg h264 failed: %s", (r.stderr or r.stdout or "")[:300])
                return False
            return dst.is_file() and dst.stat().st_size > 500
        except Exception as e:
            log.warning("ffmpeg h264 error: %s", e)
            return False


# Process-wide buffer (streamer + deck + clutchbot share this)
_buffer: HdmiClipBuffer | None = None
_buffer_lock = threading.Lock()


def get_clip_buffer(
    seconds: float = DEFAULT_SECONDS,
    target_fps: float = DEFAULT_FPS,
    max_width: int = DEFAULT_MAX_WIDTH,
) -> HdmiClipBuffer:
    global _buffer
    with _buffer_lock:
        if _buffer is None:
            _buffer = HdmiClipBuffer(
                seconds=seconds, target_fps=target_fps, max_width=max_width
            )
            log.info(
                "HDMI ClipBuffer ready: %ss @ %.0ffps max_w=%d -> %s",
                seconds,
                target_fps,
                max_width,
                _buffer.out_dir,
            )
        return _buffer


def push_frame(frame: np.ndarray | None) -> None:
    get_clip_buffer().push(frame)


def get_latest_jpeg() -> bytes | None:
    """Newest JPEG from the shared HDMI ring (for Deck LIVE MJPEG)."""
    return get_clip_buffer().latest_jpeg()


def get_latest_frame() -> tuple[bytes, int] | None:
    """Newest (jpeg, seq) from the shared HDMI ring."""
    return get_clip_buffer().latest_frame()


def export_clip(seconds: float | None = None, path: str | Path | None = None) -> ClipExportResult | None:
    return get_clip_buffer().export(path=path, seconds=seconds)
