"""WP-B: armed-but-unwritten stop-flush. Never a ghost clip_id on Recap."""

from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import numpy as np

from qoresence.foundry.session_view import recap_from_envelope
from qoresence.vision.clip_buffer import HdmiClipBuffer


def _jpeg(w: int = 160, h: int = 100) -> bytes:
    frame = np.full((h, w, 3), (20, 180, 40), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    return buf.tobytes()


def _fake_h264(src: Path, dst: Path, fps: float) -> bool:
    import shutil

    if src.exists():
        shutil.copy(src, dst)
        return True
    return False


def test_not_armed_flush_is_honest_and_has_no_clip_id(tmp_path: Path):
    buf = HdmiClipBuffer(seconds=2, target_fps=10, max_width=160, out_dir=tmp_path)
    rec = buf.flush_armed()
    assert rec["armed"] is False
    assert rec["written"] is False
    assert rec["clip_id"] is None
    assert rec["reason"] == "not_armed"
    assert list(tmp_path.glob("hdmi_clip_*")) == []


def test_armed_no_frames_is_armed_no_file_not_ghost(tmp_path: Path):
    buf = HdmiClipBuffer(seconds=2, target_fps=10, max_width=160, out_dir=tmp_path)
    buf.note_arm(clock_ns=1, reason="unit")
    rec = buf.flush_armed()
    assert rec["armed"] is True
    assert rec["written"] is False
    assert rec["clip_id"] is None
    assert rec["reason"] == "armed_no_file"
    assert list(tmp_path.glob("hdmi_clip_*")) == []


def test_armed_with_frames_writes_stem(tmp_path: Path, monkeypatch):
    buf = HdmiClipBuffer(seconds=2, target_fps=10, max_width=160, out_dir=tmp_path)
    jpg = _jpeg()
    now = time.monotonic()
    for i in range(5):
        buf._frames.append((now + i * 0.1, jpg, 160, 100, i + 1))
    monkeypatch.setattr(HdmiClipBuffer, "_ffmpeg_h264", staticmethod(_fake_h264))
    buf.note_arm(clock_ns=2, reason="unit")
    rec = buf.flush_armed()
    assert rec["armed"] is True
    assert rec["written"] is True
    assert rec["clip_id"]
    assert rec["clip_id"].startswith("hdmi_clip_")
    path = Path(rec["path"])
    assert path.is_file()
    assert rec["clip_id"] == path.stem


def test_recap_does_not_gain_ghost_clip_from_armed_no_file():
    view = {
        "schema_version": "session-view-1",
        "session_id": "qoresence_06b8c404882b",
        "persisted": True,
        "events": [
            {
                "event_id": "qoresence_06b8c404882b_evt_0001",
                "event_type": "situation_shift",
                "t_start_ns": 1_000_000,
                "t_end_ns": 1_000_000,
                "qualification": "confirmed",
                "bodied": False,
                "clip": {"available": False},
            }
        ],
    }
    recap = recap_from_envelope(
        {
            "ok": True,
            "status": "live",
            "session": "qoresence_06b8c404882b",
            "view": view,
            "freshness": {
                "generated_at": "2026-09-13T15:08:23Z",
                "last_event_at": None,
                "age_ms": 0,
                "stale": False,
            },
        }
    )
    assert recap["linked_clip_count"] == 0
    assert recap["events"][0]["clip"] == {"available": False}
    assert "hdmi_clip_" not in json.dumps(recap["events"][0].get("clip") or {})
