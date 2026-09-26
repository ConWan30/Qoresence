"""Stem Record — drop-oldest queue, wall-clock paced mux; never a 1.0 gate."""

from __future__ import annotations

import itertools
import shutil
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from qoresence.stem.record import GAP_DARK_S, QUEUE_MAX, StemRecord

S = 1_000_000_000


def _jpeg(value: int = 128, w: int = 64, h: int = 48) -> bytes:
    img = np.full((h, w, 3), value, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


def _armed(tmp_path: Path, fps: float = 10.0) -> StemRecord:
    rec = StemRecord(bus=None, out_dir=str(tmp_path), fps=fps)
    rec._start_ns = 0
    rec._raw_path = tmp_path / "stem_test_raw.avi"
    rec._path = tmp_path / "stem_test.mp4"
    return rec


def test_enqueue_drop_oldest_does_not_block():
    rec = StemRecord(bus=None, out_dir="clips")
    rec._active = True
    for i in range(QUEUE_MAX + 25):
        rec.enqueue_jpeg(b"jpeg-%d" % i, ts_ns=i)
    assert rec._q.qsize() <= QUEUE_MAX
    snap = rec.snapshot()
    assert snap["dropped"] >= 25
    assert snap["queued"] <= QUEUE_MAX


def test_frames_paced_to_wall_clock(tmp_path):
    rec = _armed(tmp_path, fps=10.0)
    try:
        rec._write_frame(0, _jpeg())
        rec._write_frame(int(0.3 * S), _jpeg())
        rec._write_frame(int(0.35 * S), _jpeg())
        # 0.3 s at 10 fps → frame index 3; small gap repeats the frame, no dark
        assert rec._frames_out == 4
        assert rec._dark_frames == 0
    finally:
        rec._release_writer()


def test_long_gap_written_dark_not_frozen(tmp_path):
    rec = _armed(tmp_path, fps=10.0)
    try:
        rec._write_frame(0, _jpeg())
        gap_s = GAP_DARK_S + 1.5
        rec._write_frame(int(gap_s * S), _jpeg())
        assert rec._frames_out == int(gap_s * 10) + 1
        assert rec._dark_frames == int(gap_s * 10) - 1
    finally:
        rec._release_writer()


def test_late_frame_dropped(tmp_path):
    rec = _armed(tmp_path, fps=10.0)
    try:
        rec._write_frame(0, _jpeg())
        rec._write_frame(int(0.5 * S), _jpeg())
        before = rec._frames_out
        rec._write_frame(int(0.2 * S), _jpeg())
        assert rec._frames_out == before
        assert rec.snapshot()["late"] == 1
    finally:
        rec._release_writer()


def test_mismatched_size_resized(tmp_path):
    rec = _armed(tmp_path, fps=10.0)
    try:
        rec._write_frame(0, _jpeg(w=64, h=48))
        rec._write_frame(int(0.1 * S), _jpeg(w=32, h=24))
        assert rec._size == (64, 48)
        assert rec._frames_out == 2
    finally:
        rec._release_writer()


def test_stop_passes_clock_window_to_chapters(tmp_path, monkeypatch):
    from qoresence.stem import record as record_mod
    from qoresence.vision import clip_chapters

    calls = []

    def fake_chapters(path, duration_s, *, window_start_ns=None, window_end_ns=None):
        calls.append((path, duration_s, window_start_ns, window_end_ns))

    ticks = itertools.chain([1 * S], itertools.repeat(int(7.5 * S)))
    monkeypatch.setattr(record_mod, "clock_ns", lambda: next(ticks))
    monkeypatch.setattr(clip_chapters, "chapters_after_export", fake_chapters)
    rec = StemRecord(bus=None, out_dir=str(tmp_path))
    final = tmp_path / "stem_final.mp4"
    monkeypatch.setattr(rec, "_finalize", lambda duration_s, wav=None: final)
    rec.start()
    rec.stop()
    assert calls == [(final, 6.5, 1 * S, int(7.5 * S))]


def test_stop_enqueues_excision_only_for_h264_when_enabled(tmp_path, monkeypatch):
    from qoresence.stem import record as record_mod
    from qoresence.vision import clip_chapters, clip_excise

    calls = []
    ticks = itertools.chain([1 * S], itertools.repeat(int(7.5 * S)))
    monkeypatch.setattr(record_mod, "clock_ns", lambda: next(ticks))
    monkeypatch.setattr(clip_chapters, "chapters_after_export", lambda *a, **k: None)
    monkeypatch.setattr(clip_excise, "excise_enabled", lambda: True)
    monkeypatch.setattr(
        clip_excise, "submit_recording", lambda *a, **k: calls.append((a, k)) or True
    )
    rec = StemRecord(bus=None, out_dir=str(tmp_path))
    final = tmp_path / "stem_final.mp4"

    def fake_finalize(duration_s, wav=None):
        rec._h264 = True
        return final

    monkeypatch.setattr(rec, "_finalize", fake_finalize)
    monkeypatch.setattr(rec, "_note_still", lambda *a, **k: None)
    rec.start()
    rec._still = [(1.0, 0.2), (2.0, 0.3)]
    rec.stop()
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == (final,)
    assert kwargs["start_ns"] == 1 * S
    assert kwargs["end_ns"] == int(7.5 * S)
    assert kwargs["duration_s"] == 6.5
    assert kwargs["stillness"] == [(1.0, 0.2), (2.0, 0.3)]


def test_stop_skips_excision_when_off_or_not_h264(tmp_path, monkeypatch):
    from qoresence.stem import record as record_mod
    from qoresence.vision import clip_chapters, clip_excise

    calls = []
    ticks = itertools.chain([1 * S], itertools.repeat(int(4 * S)))
    monkeypatch.setattr(record_mod, "clock_ns", lambda: next(ticks))
    monkeypatch.setattr(clip_chapters, "chapters_after_export", lambda *a, **k: None)
    monkeypatch.setattr(clip_excise, "submit_recording", lambda *a, **k: calls.append(1) or True)
    rec = StemRecord(bus=None, out_dir=str(tmp_path))
    monkeypatch.setattr(rec, "_finalize", lambda duration_s, wav=None: tmp_path / "stem_raw.avi")
    rec.start()
    rec.stop()
    assert calls == []


def test_note_still_samples_about_ten_hertz():
    import numpy as np

    rec = StemRecord(bus=None, out_dir="clips")
    rec._start_ns = 0
    a = np.full((72, 128, 3), 10, dtype=np.uint8)
    b = np.full((72, 128, 3), 200, dtype=np.uint8)
    rec._note_still(a, 0)
    rec._note_still(a, int(0.05 * S))
    rec._note_still(b, int(0.2 * S))
    assert len(rec._still) == 1
    assert rec._still[0][0] == 0.2
    assert rec._still[0][1] > 10


def test_stop_without_frames_writes_no_sidecar(tmp_path, monkeypatch):
    from qoresence.vision import clip_buffer

    monkeypatch.setattr(clip_buffer, "get_latest_frame", lambda: None)
    rec = StemRecord(bus=None, out_dir=str(tmp_path))
    rec.start()
    rec.stop()
    assert list(tmp_path.glob("*.chapters.json")) == []
    assert rec.snapshot()["frames_out"] == 0


def _run_live(tmp_path, monkeypatch, seconds: float = 0.6) -> StemRecord:
    from qoresence.vision import clip_buffer

    seq = itertools.count(1)
    frames = [_jpeg(40), _jpeg(200)]
    monkeypatch.setattr(clip_buffer, "get_latest_frame", lambda: (frames[next(seq) % 2], next(seq)))
    rec = StemRecord(bus=None, out_dir=str(tmp_path), fps=10.0)
    rec.start()
    time.sleep(seconds)
    rec.stop()
    return rec


def test_end_to_end_keeps_raw_when_ffmpeg_missing(tmp_path, monkeypatch):
    from qoresence.vision.clip_buffer import HdmiClipBuffer

    monkeypatch.setattr(HdmiClipBuffer, "_ffmpeg_h264", staticmethod(lambda *a, **k: False))
    rec = _run_live(tmp_path, monkeypatch)
    snap = rec.snapshot()
    assert snap["h264"] is False
    final = Path(snap["path"])
    assert final.suffix == ".avi" and final.is_file()
    assert snap["frames_out"] >= 2
    assert (tmp_path / (final.stem + ".chapters.json")).is_file()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_end_to_end_h264_mp4(tmp_path, monkeypatch):
    rec = _run_live(tmp_path, monkeypatch)
    snap = rec.snapshot()
    assert snap["h264"] is True
    final = Path(snap["path"])
    assert final.suffix == ".mp4" and final.is_file()
    assert not list(tmp_path.glob("*_raw.avi"))
    assert (tmp_path / (final.stem + ".chapters.json")).is_file()
    cap = cv2.VideoCapture(str(final))
    try:
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    finally:
        cap.release()
    assert abs(n - snap["frames_out"]) <= 2
