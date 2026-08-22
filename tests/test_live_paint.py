"""Dark Theater + Same-Seq render rules."""

from __future__ import annotations

import numpy as np

from qoresence.deck.live_paint import decide_live_paint, is_blank_bgr, is_play_state
from qoresence.pilot import closeout
from tests.test_pilot_monitor import _freeze_row


def test_blank_frame_goes_dark():
    blank = np.zeros((32, 48, 3), dtype=np.uint8)
    assert is_blank_bgr(blank) is True
    d = decide_live_paint(has_frame=True, live_seq=4, widget_seq=4, frame=blank)
    assert d.paint is False
    assert d.reason == "blank"
    noisy = np.arange(32 * 48 * 3, dtype=np.uint8).reshape(32, 48, 3)
    d2 = decide_live_paint(has_frame=True, live_seq=4, widget_seq=4, frame=noisy)
    assert d2.paint is True
    assert d2.reason == "ok"


def test_no_frame_and_not_play_go_dark():
    d = decide_live_paint(has_frame=False, live_seq=0, widget_seq=0)
    assert d.paint is False
    assert d.reason == "no_frame"
    d2 = decide_live_paint(
        has_frame=True,
        live_seq=9,
        widget_seq=9,
        game_state="menu",
        blank=False,
    )
    assert d2.paint is False
    assert d2.plane_dim is True
    assert d2.reason == "not_play"
    assert is_play_state("gameplay", "locked") is True
    assert is_play_state("paused", "locked") is False


def test_seq_skew_goes_dark_widgets_ghost():
    d = decide_live_paint(
        has_frame=True, live_seq=10, widget_seq=7, blank=False, game_state="gameplay"
    )
    assert d.paint is False
    assert d.same_seq is False
    assert d.reason == "seq_skew"
    assert d.widgets_ok() is False
    ok = decide_live_paint(
        has_frame=True, live_seq=10, widget_seq=10, blank=False, game_state="gameplay"
    )
    assert ok.paint is True
    assert ok.same_seq is True
    assert ok.widgets_ok() is True


def test_plane_dim_sleeps_board_on_pause():
    d = decide_live_paint(
        has_frame=True,
        live_seq=3,
        widget_seq=3,
        game_state="paused",
        title_hysteresis="locked",
        blank=False,
    )
    assert d.plane_dim is True
    assert d.widgets_ok() is False
    assert d.reason == "not_play"


def test_last_good_live_paint_counts_in_excluding_deck_lock():
    samples = [
        _freeze_row("t0", [], has_frame=True, video_age_s=0.1, frames=10),
        _freeze_row("t1", [], has_frame=True, live_paint=False, video_age_s=0.2, frames=10),
        _freeze_row("t2", [], has_frame=True, live_paint=False, video_age_s=0.3, frames=10),
        _freeze_row("t3", [], has_frame=True, live_paint=True, video_age_s=0.1, frames=12),
    ]
    summary = closeout.summarize(samples)
    assert summary["freeze_events"] >= 1
    assert summary["freeze_events_by_kind"]["card_stall"] >= 1
    assert summary["freeze_events_excluding_deck_lock"] >= 1
    assert summary["freeze_events_by_kind"]["deck_lock"] == 0
