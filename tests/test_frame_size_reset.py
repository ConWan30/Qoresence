"""Frame size changes (capture rebind / new mode) must not kill the video path.

Live 2026-10-13 (live-285): after an 18 s stall and a capture rebind,
``StreamerRuntime._process_frame`` raised a cv2 size mismatch
(``absdiff(gray, _prev_gray)``) that ended the ``qoresence-streamer`` thread,
and game detection's Farneback flow asserted on every tick after.
"""

from __future__ import annotations

import numpy as np

from tests.test_capture_rebind_race import _runtime


def _gray(h, w, v=90):
    return np.full((h, w), v, dtype=np.uint8)


def test_process_frame_rebaselines_on_size_change():
    rt, bus, td = _runtime()
    try:
        rt._process_frame(_gray(360, 640), 1.0)
        rt._process_frame(_gray(360, 640, 100), 1.03)
        assert rt._last_motion > 0
        rt._process_frame(_gray(180, 320, 10), 1.06)  # different size: no raise
        assert rt._last_motion == 0.0
        assert rt._prev_gray.shape == (180, 320)
        rt._process_frame(_gray(180, 320, 20), 1.09)
        assert rt._last_motion > 0
    finally:
        bus.close()
        td.cleanup()


def test_loop_supervisor_survives_exceptions():
    rt, bus, td = _runtime()
    try:
        rt._running = True
        calls = {"n": 0}

        def body():
            calls["n"] += 1
            if calls["n"] <= 2:
                rt._prev_gray = _gray(4, 4)
                raise RuntimeError("bad frame")
            rt._running = False

        rt._run_loop_body = body  # type: ignore[method-assign]
        rt._run_loop()
        assert calls["n"] == 3
        assert rt._loop_errors == 2
        assert rt._prev_gray is None
    finally:
        bus.close()
        td.cleanup()


def test_motion_tracker_size_change_does_not_assert():
    from qoresence.vision.motion_tracker import MotionTracker

    tr = MotionTracker()
    rng = np.random.default_rng(0)
    tr.analyze(rng.integers(0, 255, (720, 1280, 3), dtype=np.uint8))
    tr.analyze(rng.integers(0, 255, (720, 1280, 3), dtype=np.uint8))
    ev = tr.analyze(rng.integers(0, 255, (360, 640, 3), dtype=np.uint8))
    assert ev.raw_details.get("first_frame") is True
    tr.analyze(rng.integers(0, 255, (360, 640, 3), dtype=np.uint8))
