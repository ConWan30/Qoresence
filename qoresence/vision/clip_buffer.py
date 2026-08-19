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
# Full-rate ring when Qoresence owns the card (PS5 HDMI 60 Hz → Deck LIVE 60).
# Lower with get_clip_buffer(target_fps=30) or GET /video?fps=30 if CPU/RAM tight.
DEFAULT_FPS = 60.0
# Smaller LIVE JPEGs = faster encode + less browser MJPEG buffer lag.
DEFAULT_MAX_WIDTH = 640
# Slightly lower quality keeps 60fps LIVE from saturating CPU (freeze root cause)
DEFAULT_JPEG_QUALITY = 48
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
        # Never Path.resolve() under _lock — Windows realpath can hang and
        # freeze Deck /health plus every push() waiter (live 2026-08-14).
        self._out_dir_str = str(self.out_dir)
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
        # Fast path for LIVE MJPEG (overwritten every successful encode)
        self._live_jpeg: bytes | None = None
        self._live_seq: int = 0
        self._live_ts: float = 0.0
        self._pending: np.ndarray | None = None
        self._pending_lock = threading.Lock()
        self._pending_event = threading.Event()
        self._worker: threading.Thread | None = None

    def enable(self, on: bool = True) -> None:
        self._enabled = bool(on)

    def enqueue(self, frame: np.ndarray | None) -> None:
        """Copy latest BGR and encode on a worker. Capture loop must not JPEG."""
        if not self._enabled or frame is None:
            return
        try:
            if not hasattr(frame, "shape") or len(frame.shape) < 2:
                return
            snap = np.ascontiguousarray(frame)
            if snap is frame:
                snap = frame.copy()
        except Exception:
            return
        with self._pending_lock:
            self._pending = snap
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(
                    target=self._encode_loop, name="clip-jpeg", daemon=True
                )
                self._worker.start()
        self._pending_event.set()

    def _encode_loop(self) -> None:
        while self._enabled:
            self._pending_event.wait(timeout=1.0)
            self._pending_event.clear()
            with self._pending_lock:
                fr = self._pending
                self._pending = None
            if fr is None:
                continue
            try:
                self.push(fr)
            except Exception as e:
                log.debug("ClipBuffer worker encode failed: %s", e)

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
                # INTER_LINEAR is much faster than INTER_AREA for LIVE path
                small = cv2.resize(frame, (self.max_width, nh), interpolation=cv2.INTER_LINEAR)
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
            jpeg = buf.tobytes()
            with self._lock:
                self._seq += 1
                self._frames.append((now, jpeg, sw, sh, self._seq))
                # Dedicated latest slot for LIVE (always newest, no ring scan)
                self._live_jpeg = jpeg
                self._live_seq = self._seq
                self._live_ts = now
                self._pushes += 1
        except Exception as e:
            log.debug("ClipBuffer push failed: %s", e)

    def latest_jpeg(self) -> bytes | None:
        """Return newest JPEG bytes (LIVE slot, no re-encode). Empty → None."""
        with self._lock:
            if self._live_jpeg is not None:
                return self._live_jpeg
            if not self._frames:
                return None
            return self._frames[-1][1]

    def latest_frame(self) -> tuple[bytes, int] | None:
        """Return (jpeg_bytes, seq) for newest frame. Empty → None."""
        with self._lock:
            if self._live_jpeg is not None and self._live_seq > 0:
                return (self._live_jpeg, self._live_seq)
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
            live_ts = self._live_ts or (self._frames[-1][0] if n else 0.0)
            age_s = (now - live_ts) if live_ts else None
            seq = self._live_seq or (self._frames[-1][4] if n else 0)
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
                "out_dir": self._out_dir_str,
                "has_frame": n > 0 or self._live_jpeg is not None,
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
            # Walk backward until we cover `seconds` AND enough frames to
            # encode at the 5 fps floor. A timestamp window after a push
            # stall used to yield 7–13s clips that opened on the score banner.
            want = max(0.5, seconds)
            min_frames = max(2, int(want * 5.0))
            picked: list = []
            for frame in reversed(self._frames):
                picked.append(frame)
                span = picked[0][0] - picked[-1][0]
                if span >= want and len(picked) >= min_frames:
                    break
            picked.reverse()
            if len(picked) < 2:
                picked = list(self._frames)
            snapshot = list(picked)

        if len(snapshot) < 2:
            log.warning("ClipBuffer export: need >=2 frames, have %d", len(snapshot))
            return None

        w = snapshot[0][2]
        h = snapshot[0][3]
        # force consistent size (entries: ts, jpeg, w, h, seq)
        for entry in snapshot:
            if len(entry) >= 4:
                w, h = int(entry[2]), int(entry[3])
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
            for entry in snapshot:
                # (ts, jpeg, w, h[, seq])
                jpg = entry[1]
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
                raw_path.unlink(missing_ok=True)
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
        # Optional InputRing + chapter sidecars (best-effort; never fail MP4 export)
        try:
            _write_buttons_sidecar(final_path, duration_s=dur)
        except Exception as e:
            log.debug("buttons sidecar skipped: %s", e)
        try:
            from qoresence.vision.clip_chapters import chapters_after_export

            chapters_after_export(final_path, duration_s=dur)
        except Exception as e:
            log.debug("chapters sidecar skipped: %s", e)
        try:
            _write_otel_sidecar(final_path, snapshot=snapshot)
        except Exception as e:
            log.debug("otel sidecar skipped: %s", e)
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
            _buffer = HdmiClipBuffer(seconds=seconds, target_fps=target_fps, max_width=max_width)
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


def enqueue_frame(frame: np.ndarray | None) -> None:
    """Non-blocking JPEG ingest for the streamer capture thread."""
    get_clip_buffer().enqueue(frame)


def get_latest_jpeg() -> bytes | None:
    """Newest JPEG from the shared HDMI ring (for Deck LIVE MJPEG)."""
    return get_clip_buffer().latest_jpeg()


def get_latest_frame() -> tuple[bytes, int] | None:
    """Newest (jpeg, seq) from the shared HDMI ring."""
    return get_clip_buffer().latest_frame()


def export_clip(
    seconds: float | None = None, path: str | Path | None = None
) -> ClipExportResult | None:
    return get_clip_buffer().export(path=path, seconds=seconds)


def _write_buttons_sidecar(mp4_path: Path, duration_s: float) -> Path | None:
    """Write clips/<stem>.buttons.json from InputRing snapshot. Never raises to caller."""
    import json

    try:
        from qoresence.sync.input_ring import get_input_ring
    except Exception:
        return None
    try:
        seconds = max(0.5, float(duration_s) if duration_s else 5.0)
        events = get_input_ring().snapshot(seconds=seconds)
        if not events:
            return None
        # Sibling: foo.mp4 → foo.buttons.json
        out = Path(mp4_path).with_name(Path(mp4_path).stem + ".buttons.json")
        names = [e.get("name") for e in events if e.get("kind") in ("press", "trigger")]
        summary: dict[str, int] = {}
        for n in names:
            if n:
                summary[str(n)] = summary.get(str(n), 0) + 1
        payload = {
            "duration_s": round(float(seconds), 3),
            "events": events,
            "buttons_summary": summary,
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log.info("buttons sidecar: %s (%d events)", out.name, len(events))
        return out
    except Exception as e:
        log.debug("buttons sidecar write failed: %s", e)
        return None


def _write_otel_sidecar(
    mp4_path: Path,
    snapshot: list[tuple[float, bytes, int, int, int]],
) -> Path | None:
    """Write clips/<stem>.otel.json with trace IDs overlapping the clip window.

    Trace IDs come from the active OTel exporter's short-cascade ring. If OTel
    is disabled or no cascades overlap the clip window, the sidecar is skipped.
    """
    import json

    try:
        from qoresence.observability.otel import get_otel_exporter

        exporter = get_otel_exporter()
        if exporter is None or not exporter.enabled:
            return None
    except Exception:
        return None

    try:
        if not snapshot:
            return None
        start_s = snapshot[0][0]
        end_s = snapshot[-1][0]
        start_ns = int(start_s * 1_000_000_000)
        end_ns = int(end_s * 1_000_000_000)
        trace_ids = exporter.trace_ids_for_window(start_ns, end_ns)
        if not trace_ids:
            return None

        out = Path(mp4_path).with_name(Path(mp4_path).stem + ".otel.json")
        jaeger_base = "http://127.0.0.1:16686/trace"
        payload = {
            "clip.clock_ns.start": start_ns,
            "clip.clock_ns.end": end_ns,
            "trace.ids": trace_ids,
            "jaeger_urls": [f"{jaeger_base}/{tid}" for tid in trace_ids],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log.info("otel sidecar: %s (%d trace ids)", out.name, len(trace_ids))
        return out
    except Exception as e:
        log.debug("otel sidecar write failed: %s", e)
        return None


def buttons_summary_for_export(duration_s: float = 5.0) -> dict[str, int]:
    """Compact button counts for Deck moment payload (empty if no ring/inputs)."""
    try:
        from qoresence.sync.input_ring import get_input_ring

        events = get_input_ring().snapshot(seconds=max(0.5, float(duration_s)))
        summary: dict[str, int] = {}
        for e in events:
            if e.get("kind") in ("press", "trigger") and e.get("name"):
                n = str(e["name"])
                summary[n] = summary.get(n, 0) + 1
        return summary
    except Exception:
        return {}
