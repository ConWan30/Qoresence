"""Stem Record — drop-oldest queue; never a 1.0 gate."""

from __future__ import annotations

import itertools

from qoresence.stem.record import QUEUE_MAX, StemRecord


def test_enqueue_drop_oldest_does_not_block():
    rec = StemRecord(bus=None, out_dir="clips")
    rec._active = True
    for i in range(QUEUE_MAX + 25):
        rec.enqueue_jpeg(b"jpeg-%d" % i, ts_ns=i)
    assert rec._q.qsize() <= QUEUE_MAX
    snap = rec.snapshot()
    assert snap["dropped"] >= 25
    assert snap["queued"] <= QUEUE_MAX


def test_stop_passes_clock_window_to_chapters(tmp_path, monkeypatch):
    from qoresence.stem import record as record_mod
    from qoresence.vision import clip_chapters

    calls = []

    def fake_chapters(path, duration_s, *, window_start_ns=None, window_end_ns=None):
        calls.append((path, duration_s, window_start_ns, window_end_ns))

    ticks = itertools.chain([1_000_000_000], itertools.repeat(7_500_000_000))
    monkeypatch.setattr(record_mod, "clock_ns", lambda: next(ticks))
    monkeypatch.setattr(clip_chapters, "chapters_after_export", fake_chapters)
    rec = StemRecord(bus=None, out_dir=str(tmp_path))
    rec.start()
    rec.stop()
    assert len(calls) == 1
    _path, duration_s, start_ns, end_ns = calls[0]
    assert (start_ns, end_ns) == (1_000_000_000, 7_500_000_000)
    assert duration_s == 6.5
