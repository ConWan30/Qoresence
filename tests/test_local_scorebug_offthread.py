"""Local scorebug stays off the capture path and avoids needless frame copies."""

from __future__ import annotations

import threading
import time

import numpy as np

from qoresence.vision.local_scorebug.service import LocalScorebugService


class _Reader:
    model_id = "fake"

    def __init__(self) -> None:
        self.reads = 0

    def read(self, frame):  # pragma: no cover - not reached in these tests
        self.reads += 1
        raise AssertionError("should not read")


def test_wants_sample_matches_observe_rate_limit():
    svc = LocalScorebugService(reader=_Reader())
    assert svc.wants_sample({"seq": 1, "clock_ns": 1_000_000_000}) is True
    with svc._lock:
        svc._last_seq = 1
        svc._last_sample_ns = 1_000_000_000
    assert svc.wants_sample({"seq": 1, "clock_ns": 1_000_000_000}) is False  # same frame
    assert svc.wants_sample({"seq": 2, "clock_ns": 1_050_000_000}) is False  # < 200 ms
    assert svc.wants_sample({"seq": 3, "clock_ns": 1_300_000_000}) is True
    assert svc.current("s") is None


def test_local_board_skips_full_frame_copy_when_not_due(monkeypatch):
    from qoresence.monitor import frame_hub as fh
    from qoresence.vision import scoreboard_extractor as se
    from qoresence.vision.local_scorebug import service as svc_mod

    svc = LocalScorebugService(reader=_Reader())
    with svc._lock:
        svc._last_seq = 7
        svc._last_sample_ns = 5
    monkeypatch.setattr(svc_mod, "_SERVICE", svc)
    monkeypatch.delenv("QORESENCE_LOCAL_SCOREBUG", raising=False)

    hub = fh.FrameHub()
    hub.publish(np.full((72, 128, 3), 50, dtype=np.uint8), clock_ns=5, seq=7)
    copies = {"n": 0}
    orig = hub.get_latest_observation

    def _counting():
        copies["n"] += 1
        return orig()

    hub.get_latest_observation = _counting  # type: ignore[method-assign]
    monkeypatch.setattr(fh, "get_frame_hub", lambda: hub)
    out = se._local_scorebug_board(np.zeros((72, 128, 3), np.uint8), None, False)
    assert out is None
    assert copies["n"] == 0


def test_scoreboard_offer_never_blocks_on_slow_extract(monkeypatch):
    """The capture/visual side only enqueues; a slow local read cannot stall it."""
    from qoresence.vision import scoreboard_lock as sl
    from qoresence.vision.scoreboard_extractor import FootballScoreboardExtractor

    gate = threading.Event()
    seen_threads: list[str] = []

    def _slow_extract(self, frame, ctx=None, *, allow_ocr=None):
        seen_threads.append(threading.current_thread().name)
        gate.wait(2.0)
        return ctx

    monkeypatch.setattr(FootballScoreboardExtractor, "extract", _slow_extract)
    w = sl.ScoreboardLockWorker()
    frame = np.zeros((72, 128, 3), np.uint8)
    t0 = time.monotonic()
    for _ in range(20):
        w.offer(frame, None)
    assert time.monotonic() - t0 < 0.5
    gate.set()
    w.wait(2.0)
    w.stop()
    assert seen_threads and all(n == "scoreboard-lock" for n in seen_threads)
