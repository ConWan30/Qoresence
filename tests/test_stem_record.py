"""Stem Record — drop-oldest queue; never a 1.0 gate."""

from __future__ import annotations

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
