"""Local scorebug live visibility: throttled INFO summary + /health fields."""

from __future__ import annotations

import logging

import numpy as np

from qoresence.vision.local_scorebug.agreement import AgreementConfig
from qoresence.vision.local_scorebug.service import (
    SUMMARY_INTERVAL_NS,
    LocalScorebugService,
)
from tests.local_scorebug_helpers import frame_from_band

S = 1_000_000_000
LOGGER = "qoresence.vision.local_scorebug.service"


def _summaries(caplog):
    return [r.getMessage() for r in caplog.records if "local scorebug " in r.getMessage()]


def test_summary_is_info_and_throttled(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    svc = LocalScorebugService()
    blank = np.full((360, 640, 3), (40, 90, 40), np.uint8)
    t0 = 10 * S
    # 0.5 s cadence for 65 s: two full 30 s windows -> exactly two INFO lines.
    for i in range(131):
        now = t0 + i * S // 2
        svc.observe(blank, stamp={"seq": i, "clock_ns": now}, session_id="s", now_ns=now)
    lines = _summaries(caplog)
    assert len(lines) == 2, lines
    assert all(
        r.levelno == logging.INFO for r in caplog.records if "local scorebug " in r.getMessage()
    )
    assert "reads=61" in lines[0] and "agreed=0" in lines[0]
    assert "last_blank=layout_unknown" in lines[0]
    assert "frame=360x640x3" in lines[0]
    st = svc.stats()
    assert st["blank_reasons"]["layout_unknown"] == 131
    assert st["last_frame_shape"] == [360, 640, 3]
    assert "logo_ncc" in (st["last_detail"] or {})


def test_summary_counts_agreed_reads(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    svc = LocalScorebugService(config=AgreementConfig())
    frame = frame_from_band("std_29_15_4th_2-38")
    t0 = 5 * S
    n = int(SUMMARY_INTERVAL_NS // (S // 2)) + 2
    for i in range(n):
        now = t0 + i * S // 2
        svc.observe(frame, stamp={"seq": i, "clock_ns": now}, session_id="s", now_ns=now)
    lines = _summaries(caplog)
    assert len(lines) == 1
    assert "state=sure" in lines[0] and "agreed=" in lines[0] and "agreed=0" not in lines[0]


def test_skips_and_errors_reach_health(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    svc = LocalScorebugService()
    svc.note_skip("college_profile", now_ns=1 * S)
    svc.note_error(RuntimeError("boom"), now_ns=2 * S)
    svc.note_skip("college_profile", now_ns=1 * S + SUMMARY_INTERVAL_NS + 1)
    st = svc.stats()
    assert st["skips"] == {"college_profile": 2}
    assert st["last_skip"] == "college_profile"
    assert st["errors"] == 1 and st["last_error"] == "RuntimeError: boom"
    lines = _summaries(caplog)
    assert len(lines) == 1 and "skips=[college_profile=2]" in lines[0]
    assert "last_error=RuntimeError: boom" in lines[0]


def test_reader_exception_is_counted_not_raised():
    from qoresence.vision.local_scorebug.profile import MADDEN27_STANDARD

    class _Boom:
        model_id = "x"
        profile = MADDEN27_STANDARD

        def read(self, frame):
            raise ValueError("bad frame")

    svc = LocalScorebugService(reader=_Boom())  # type: ignore[arg-type]
    out = svc.observe(np.zeros((360, 640, 3), np.uint8), stamp={"seq": 1, "clock_ns": S}, now_ns=S)
    assert out is None
    assert svc.stats()["errors"] == 1
    assert "bad frame" in svc.stats()["last_error"]


def test_health_carries_local_scorebug_where_the_deck_reads_it():
    """Deck (glass signal-meter) reads health.state.local_scorebug ?? health.local_scorebug."""
    import pytest

    try:
        from fastapi.testclient import TestClient
    except Exception:
        pytest.skip("httpx/starlette TestClient not installed")
    from qoresence.deck.server import create_app
    from qoresence.vision.local_scorebug import reset_local_scorebug

    reset_local_scorebug()
    app = create_app()
    if app is None:
        pytest.skip("fastapi not installed")
    body = TestClient(app).get("/health").json()
    for block in (body["state"]["local_scorebug"], body["local_scorebug"]):
        for key in (
            "enabled",
            "state",
            "reason",
            "reads",
            "agreed",
            "last_frame_reason",
            "blank_reasons",
            "skips",
            "errors",
            "last_error",
        ):
            assert key in block, key
    reset_local_scorebug()
