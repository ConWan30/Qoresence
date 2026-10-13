"""Live Madden 27 frames (2026-10-13, NO at NYG) and the sampler pump.

On that run the reader itself was fine (these strips read correctly), but the
service only sampled when the visual lobe finished a cloud classify call
(seconds apart, 14 s on timeouts). The agreement window needs reads less than
2 s apart, so nothing ever agreed: 50 reads, 0 agreed. The pump samples the
FrameHub at the agreement rate on its own thread.
"""

from __future__ import annotations

import time

import pytest

from qoresence.vision.local_scorebug.reader import ScorebugReader
from qoresence.vision.local_scorebug.service import LocalScorebugPump, LocalScorebugService
from tests.local_scorebug_helpers import frame_from_band

LIVE = [
    ("live_9_0_2nd_4-53", (9, 0), "4:53", 2),
    ("live_10_0_2nd_3-46", (10, 0), "3:46", 2),
    ("live_10_0_2nd_1-55", (10, 0), "1:55", 2),
]
BLANK = ["live_no_strip_gameplay", "live_no_strip_paused"]


@pytest.fixture(scope="module")
def reader():
    return ScorebugReader()


@pytest.mark.parametrize("size", [(640, 360), (1280, 720), (1920, 1080)])
@pytest.mark.parametrize("name,pair,clock,quarter", LIVE)
def test_live_strip_reads_exactly(reader, name, pair, clock, quarter, size):
    r = reader.read(frame_from_band(name, size))
    assert r.ok, r.reason
    assert r.pair == pair and r.clock_text == clock and r.quarter == quarter


@pytest.mark.parametrize("size", [(640, 360), (1280, 720)])
@pytest.mark.parametrize("name", BLANK)
def test_live_no_strip_stays_blank(reader, name, size):
    r = reader.read(frame_from_band(name, size))
    assert not r.ok and r.pair is None
    assert r.reason == "layout_unknown"


def _feed(svc, frames, gap_ns):
    t0 = time.monotonic_ns() - len(frames) * gap_ns
    state = {"i": 0}

    def source():
        i = state["i"]
        if i >= len(frames):
            return None, {}
        state["i"] += 1
        return frames[i], {"seq": 100 + i, "clock_ns": t0 + i * gap_ns}

    return LocalScorebugPump(svc, source=source, session_fn=lambda: "s1"), t0


def test_sparse_cadence_never_agrees(reader):
    """The live failure: one read per cloud tick (3 s apart) never agrees."""
    svc = LocalScorebugService(reader=reader)
    frame = frame_from_band("live_10_0_2nd_3-46", (1280, 720))
    pump, _ = _feed(svc, [frame] * 6, 3_000_000_000)
    for _ in range(6):
        pump.step()
    assert svc.stats()["agreed"] == 0
    assert svc.current("s1") is None


def test_pump_cadence_agrees_and_maps_home(reader):
    svc = LocalScorebugService(reader=reader)
    frame = frame_from_band("live_10_0_2nd_3-46", (1280, 720))
    pump, _ = _feed(svc, [frame] * 4, 300_000_000)
    for _ in range(4):
        pump.step()
    assert svc.stats()["agreed"] >= 1
    # NYG (home) is drawn on the right of the strip.
    b = svc.current_for("s1", home_left=False)
    assert b is not None
    assert (b["left_score"], b["right_score"]) == (10, 0)
    assert (b["home_score"], b["away_score"]) == (0, 10)
    b2 = svc.current_for("s1", home_left=True)
    assert (b2["home_score"], b2["away_score"]) == (10, 0)
    assert svc.current_for("other-session", home_left=False) is None


def test_pump_blank_frame_breaks_agreement(reader):
    svc = LocalScorebugService(reader=reader)
    good = frame_from_band("live_10_0_2nd_3-46", (1280, 720))
    blank = frame_from_band("live_no_strip_gameplay", (1280, 720))
    pump, _ = _feed(svc, [good, good, blank, good, good], 300_000_000)
    for _ in range(5):
        pump.step()
    assert svc.stats()["agreed"] == 0
    assert svc.current("s1") is None


def test_pump_thread_runs_only_under_lease(reader):
    svc = LocalScorebugService(reader=reader)
    frame = frame_from_band("live_9_0_2nd_4-53")
    calls = {"n": 0}

    def source():
        calls["n"] += 1
        return frame, {"seq": calls["n"], "clock_ns": time.monotonic_ns()}

    pump = LocalScorebugPump(svc, lease_s=0.6, source=source, session_fn=lambda: "s1")
    assert not pump.active()
    pump.renew(game_state="gameplay", game_profile="madden_27")
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and svc.current("s1") is None:
        time.sleep(0.05)
    assert svc.current_for("s1", home_left=False)["left_score"] == 9
    time.sleep(1.0)  # lease lapses -> thread exits
    assert not pump.active()
    n = calls["n"]
    time.sleep(0.4)
    assert calls["n"] == n
    pump.stop()


def test_operator_madden_pin_overrides_cfb_classifier(monkeypatch, pin):
    from qoresence.vision import scoreboard_extractor as se

    assert se._operator_pinned_madden() is False
    monkeypatch.setenv("QORESENCE_GAME_PROFILE", "madden_27")
    assert se._operator_pinned_madden() is True
    monkeypatch.setenv("QORESENCE_GAME_PROFILE", "cfb_27")
    assert se._operator_pinned_madden() is False
    pin.set_active_pin("madden_27", pinned=True)
    assert se._operator_pinned_madden() is True
    pin.set_active_pin("madden_27", pinned=False)
    assert se._operator_pinned_madden() is False


def test_cfb_strip_blank_even_with_madden_pin(reader):
    """Fail-closed: the pin only stops the skip; a CFB strip fails the anchor."""
    r = reader.read(frame_from_band("cfb", (1280, 720)))
    assert not r.ok and r.pair is None


def _merge(monkeypatch, frame, title):
    monkeypatch.setenv("QORESENCE_EASY_OCR", "0")
    from qoresence.core import RetinaEventBus, VisualConfig
    from qoresence.lobes.visual import VisualRuntime
    from qoresence.vision.visual_context import GameCategory, GameState, VisualContext

    rt = VisualRuntime(
        VisualConfig(enabled=True, game_profile="madden_27", game_category="football"),
        RetinaEventBus(session_id="t"),
        session_head_ns=0,
    )
    ctx = VisualContext(
        game_title=title,
        game_category=GameCategory.FOOTBALL,
        game_state=GameState.GAMEPLAY,
        confidence=0.9,
    )
    return rt._merge_scoreboard(frame, ctx)


@pytest.fixture
def pin(monkeypatch):
    from qoresence.core import operator_profile as op

    monkeypatch.delenv("QORESENCE_GAME_PROFILE", raising=False)
    monkeypatch.setattr(op, "_active_pin", None)
    yield op
    monkeypatch.setattr(op, "_active_pin", None)


def test_madden_pin_beats_cfb_classifier_title(monkeypatch, pin):
    """Live 2026-10-13: the classifier said 'EA SPORTS College Football 27' on Madden."""
    pin.set_active_pin("madden_27", pinned=True)
    frame = frame_from_band("live_10_0_2nd_3-46", (1280, 720))
    out = _merge(monkeypatch, frame, "EA SPORTS College Football 27")
    assert out is not None and out.game_profile == "madden_27"


def test_unpinned_cfb_title_still_maps_cfb(monkeypatch, pin):
    frame = frame_from_band("live_10_0_2nd_3-46", (1280, 720))
    out = _merge(monkeypatch, frame, "EA SPORTS College Football 27")
    assert out is not None and out.game_profile == "cfb_27"


def test_cfb_band_misses_madden_strip_madden_band_hits():
    """Why the cloud read empty boards: the CFB crop sits above the Madden strip."""
    from qoresence.vision.scoreboard_vlm import ScoreboardVlmReferee
    from qoresence.vision.scorebug_crops import crop_misses_scorebug

    frame = frame_from_band("live_9_0_2nd_4-53", (1280, 720))
    mad = ScoreboardVlmReferee._crop(frame, game_state="gameplay", game_profile="madden_27", game_title="")
    assert mad is not None and crop_misses_scorebug(mad) is None
    cfb = ScoreboardVlmReferee._crop(frame, game_state="gameplay", game_profile="cfb_27", game_title="")
    assert cfb is None or crop_misses_scorebug(cfb) is not None
