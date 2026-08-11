"""Unit tests for HDMI clip buffer (latest_jpeg + latest_frame + stats)."""

from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

from qoresence.vision.clip_buffer import (
    DEFAULT_FPS,
    HdmiClipBuffer,
    get_clip_buffer,
    get_latest_frame,
    get_latest_jpeg,
)


def _make_jpeg(w: int = 160, h: int = 100, color: tuple[int, int, int] = (20, 180, 40)) -> bytes:
    frame = np.full((h, w, 3), color, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    return buf.tobytes()


def test_default_fps_matches_ps5_rate():
    assert DEFAULT_FPS == 60.0


def test_latest_jpeg_empty_is_none():
    buf = HdmiClipBuffer(seconds=2, target_fps=10, max_width=160)
    assert buf.latest_jpeg() is None
    assert buf.latest_frame() is None
    st = buf.stats()
    assert st["has_frame"] is False
    assert st["age_s"] is None
    assert st["frames"] == 0
    assert st["seq"] == 0


def test_latest_jpeg_after_push():
    buf = HdmiClipBuffer(seconds=2, target_fps=100, max_width=160)
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    frame[:, :] = (20, 180, 40)
    buf.push(frame)
    jpg = buf.latest_jpeg()
    assert jpg is not None
    assert isinstance(jpg, (bytes, bytearray))
    assert len(jpg) > 50
    # JPEG SOI
    assert jpg[:2] == b"\xff\xd8"
    st = buf.stats()
    assert st["has_frame"] is True
    assert st["frames"] >= 1
    assert st["age_s"] is not None
    assert st["age_s"] >= 0.0
    assert st["seq"] >= 1


def test_latest_frame_returns_seq():
    buf = HdmiClipBuffer(seconds=2, target_fps=1000, max_width=160)
    assert buf.latest_frame() is None
    f = np.full((100, 160, 3), 40, dtype=np.uint8)
    buf.push(f)
    fr = buf.latest_frame()
    assert fr is not None
    jpg, seq = fr
    assert jpg[:2] == b"\xff\xd8"
    assert seq == 1
    buf._last_push = 0.0  # bypass throttle for deterministic seq++
    buf.push(f)
    fr2 = buf.latest_frame()
    assert fr2 is not None
    assert fr2[1] == 2


def test_export_writes_mp4_and_chapters(tmp_path: Path, monkeypatch):
    """Foundry clip path: buffered frames → MP4 + chapter sidecar."""
    from qoresence.vision import clip_chapters

    buf = HdmiClipBuffer(seconds=2, target_fps=60, max_width=160, out_dir=tmp_path)
    jpg = _make_jpeg()
    # Bypass the JPEG encode in push and use a pre-made JPEG with seq.
    now = time.monotonic()
    for i in range(5):
        buf._frames.append((now + i * 0.1, jpg, 160, 100, i + 1))
    buf._live_jpeg = jpg

    # Capture sidecar calls
    chapter_calls: list[tuple[Path, float]] = []

    def fake_chapters_after_export(path: Path, duration_s: float) -> None:
        chapter_calls.append((path, duration_s))

    monkeypatch.setattr(clip_chapters, "chapters_after_export", fake_chapters_after_export)

    # Avoid ffmpeg dependency; mock h264 to copy raw AVI to final MP4.
    def fake_h264(src: Path, dst: Path, fps: float) -> bool:
        import shutil

        if src.exists():
            shutil.copy(src, dst)
            return True
        return False

    monkeypatch.setattr(HdmiClipBuffer, "_ffmpeg_h264", staticmethod(fake_h264))

    out = buf.export(path=tmp_path / "test_clip.mp4", seconds=1.0)
    assert out is not None
    out_path = Path(out.path)
    assert out_path.suffix == ".mp4"
    assert out_path.is_file()
    assert out.frames >= 2

    # Chapters should have been attempted on the final MP4.
    assert chapter_calls
    assert chapter_calls[0][0] == out_path
    assert chapter_calls[0][1] > 0


def test_get_latest_jpeg_module_helper():
    # Shared singleton may already have frames from other tests; ensure push works.
    b = get_clip_buffer(seconds=2, target_fps=50, max_width=160)
    f = np.full((100, 160, 3), 90, dtype=np.uint8)
    b.push(f)
    after = get_latest_jpeg()
    assert after is not None
    assert len(after) > 20
    assert after == b.latest_jpeg()
    fr = get_latest_frame()
    assert fr is not None
    assert fr[0] == after
