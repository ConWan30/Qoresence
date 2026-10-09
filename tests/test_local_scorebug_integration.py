"""Local scorebug end to end: keyless Madden frames -> licensed ConfirmTicket lock.

Drives the real ``FootballScoreboardExtractor.extract`` with frames published to
the FrameHub (as the capture loop does) and no cloud key, then checks the
ticket is licensed and labelled ``local_scorebug``. Unknown skins, 0-0, the
off switch, College Football and a disagreeing cloud read must stay blank.
"""

from __future__ import annotations

import time

import cv2
import pytest

from qoresence.vision.confirm_ticket import (
    get_ticket_book,
    is_seeing_source,
    mint_confirm_ticket,
    normalize_source,
    ticket_is_licensed_lock,
)
from qoresence.vision.local_scorebug import get_local_scorebug, reset_local_scorebug
from qoresence.vision.scoreboard_extractor import FootballScoreboardExtractor
from qoresence.vision.scoreboard_vlm import infer_vlm_source
from qoresence.vision.visual_context import GameCategory, GameState, VisualContext
from tests.local_scorebug_helpers import frame_from_band


class _Vlm:
    """Stand-in for the cloud referee: disabled (no key) unless given a board."""

    def __init__(self, last: dict | None = None):
        self._last = last
        self.enabled = last is not None
        self.recheck_enabled = False
        self.model = "quicksilver-pro" if last else ""
        self.base_url = ""

    def schedule(self, *a, **k):
        return None

    def get_last(self):
        return dict(self._last) if self._last else None

    def last_crop_refuse(self):
        return None

    def stats(self):
        return {"enabled": self.enabled}


@pytest.fixture
def clean(monkeypatch):
    from qoresence.monitor.frame_hub import get_frame_hub

    monkeypatch.delenv("QORESENCE_LOCAL_SCOREBUG", raising=False)
    monkeypatch.setenv("QORESENCE_EASY_OCR", "0")
    monkeypatch.setattr(
        "qoresence.vision.local_hud_digits.read_score_pair", lambda *a, **k: None, raising=False
    )
    get_ticket_book().clear()
    get_frame_hub().clear()
    reset_local_scorebug()
    FootballScoreboardExtractor._stabilizer = None
    yield
    get_ticket_book().clear()
    get_frame_hub().clear()
    reset_local_scorebug()
    FootballScoreboardExtractor._stabilizer = None


def _run(
    monkeypatch,
    fixture: str,
    *,
    vlm: _Vlm | None = None,
    profile: str = "madden_27",
    size=(1280, 720),
    n: int = 5,
):
    vlm = vlm or _Vlm()
    monkeypatch.setattr("qoresence.vision.scoreboard_vlm.get_scoreboard_vlm", lambda: vlm)
    from qoresence.monitor.frame_hub import get_frame_hub

    frame = frame_from_band(fixture, size)
    ex = FootballScoreboardExtractor()
    now = time.monotonic_ns()
    out = []
    for i in range(n):
        # 300 ms apart, newest ~0 s old (well inside the 8 s evidence window).
        get_frame_hub().publish(frame, clock_ns=now - int((n - 1 - i) * 300e6), seq=1000 + i)
        ctx = VisualContext(
            game_category=GameCategory.FOOTBALL,
            game_state=GameState.GAMEPLAY,
            confidence=0.9,
            game_profile=profile,
        )
        out.append(ex.extract(frame, ctx, allow_ocr=False))
    return out


def test_no_key_local_read_produces_licensed_lock(clean, monkeypatch):
    results = _run(monkeypatch, "std_29_15_4th_2-38")
    assert not results[0].score_vlm_locked  # one frame is never enough
    last = results[-1]
    assert last.score_vlm_locked is True
    assert last.confirm_ticket_id
    assert (last.home_score, last.away_score) == (15, 29)
    t = get_ticket_book().latest()
    assert t is not None and t.ticket_id == last.confirm_ticket_id
    assert t.source == "local_scorebug"
    assert t.model.startswith("local_scorebug_v1:madden27-standard-v1:")
    assert (t.home_score, t.away_score) == (15, 29)
    assert t.observed_crop_hash and t.observed_clock_ns
    assert ticket_is_licensed_lock(t) is True
    st = get_local_scorebug().stats()
    assert st["state"] == "sure" and st["last_choice"] == "local"


def test_no_key_lock_at_1080p(clean, monkeypatch):
    last = _run(monkeypatch, "std_14_7_2nd_1-23", size=(1920, 1080))[-1]
    assert last.score_vlm_locked is True
    assert get_ticket_book().latest().source == "local_scorebug"


@pytest.mark.parametrize("fixture", ["dark_skin", "cfb", "std_red_clock", "std_touchdown_banner"])
def test_unknown_or_dark_skin_stays_blank(clean, monkeypatch, fixture):
    for r in _run(monkeypatch, fixture, n=6):
        assert not r.score_vlm_locked
        assert not (r.confirm_ticket_id or "")
        assert r.home_score is None and r.away_score is None
    assert get_local_scorebug().stats()["agreed"] == 0


def test_zero_zero_is_never_licensed(clean, monkeypatch):
    results = _run(monkeypatch, "std_0_0_2nd_0-53", n=6)
    assert get_local_scorebug().stats()["agreed"] >= 1  # the reader is sure it is 0-0 ...
    for r in results:  # ... and the mint path still refuses to license it
        assert not r.score_vlm_locked
    t = get_ticket_book().latest()
    assert t is None or not ticket_is_licensed_lock(t)


def test_flag_off_disables_local_reader(clean, monkeypatch):
    monkeypatch.setenv("QORESENCE_LOCAL_SCOREBUG", "0")
    for r in _run(monkeypatch, "std_29_15_4th_2-38"):
        assert not r.score_vlm_locked
    assert get_local_scorebug().stats()["reads"] == 0


def test_college_football_profile_skips_local_reader(clean, monkeypatch):
    for r in _run(monkeypatch, "std_29_15_4th_2-38", profile="ncaa_football_27"):
        assert not r.score_vlm_locked
    assert get_local_scorebug().stats()["reads"] == 0


def test_cloud_cross_check_disagreement_blanks(clean, monkeypatch):
    cloud = _Vlm(
        {
            "home_score": 15,
            "away_score": 22,
            "quarter": 4,
            "home_left": False,
            "clock": "2:38",
            "left_team": "NYJ",
            "right_team": "BUF",
        }
    )
    results = _run(monkeypatch, "std_29_15_4th_2-38", vlm=cloud, n=6)
    # Before the local reader is sure, the cloud board behaves as today ...
    assert results[0].score_vlm_locked is True
    # ... once the local reader is sure of a different pair, the board blanks.
    for r in results[2:]:
        assert not r.score_vlm_locked
        assert r.home_score is None and r.away_score is None
    st = get_local_scorebug().stats()
    assert st["cross_check_disagree"] >= 1 and st["last_choice"] == "cross_check_disagree"


def test_cloud_cross_check_agreement_locks_as_local(clean, monkeypatch):
    cloud = _Vlm(
        {
            "home_score": 15,
            "away_score": 29,
            "quarter": 4,
            "home_left": False,
            "clock": "2:38",
            "left_team": "NYJ",
            "right_team": "BUF",
        }
    )
    last = _run(monkeypatch, "std_29_15_4th_2-38", vlm=cloud)[-1]
    assert last.score_vlm_locked is True
    t = get_ticket_book().latest()
    assert t.source == "local_scorebug"  # provenance names who read the digits
    assert get_local_scorebug().stats()["last_choice"] == "local_cloud_agree"


def test_provenance_label():
    board = {"_source": "local_scorebug", "_model": "local_scorebug_v1:x:y"}
    assert (
        infer_vlm_source("quicksilver-pro", "https://api.example", board=board) == "local_scorebug"
    )
    assert infer_vlm_source("local_scorebug_v1:madden27-standard-v1:abc") == "local_scorebug"
    # Cloud boards keep their own labels.
    assert infer_vlm_source("quicksilver-pro", "") != "local_scorebug"
    assert infer_vlm_source("gemini-3.8-flash", "", board={"home_score": 1}) == "gemini"
    assert is_seeing_source("local_scorebug") is True
    assert normalize_source("local") == "local_scorebug"
    t = mint_confirm_ticket(
        session_id="s", clock_ns=1, home_score=7, away_score=3, source="local_scorebug"
    )
    assert t.source == "local_scorebug"


def test_local_board_image_crop_hash_matches_frame():
    """The reader binds tickets to the published frame's crop hash, not a fresh one."""
    from qoresence.vision.local_scorebug import LocalScorebugService

    svc = LocalScorebugService()
    f = frame_from_band("std_14_7_2nd_1-23")
    b = None
    for i, t in enumerate((1000, 1250, 1500)):
        b = svc.observe(
            f,
            stamp={"seq": i, "clock_ns": t * 1_000_000, "crop_hash": "hub-hash"},
            session_id="s",
            now_ns=t * 1_000_000,
        )
    assert b is not None and b["_observation"]["crop_hash"] == "hub-hash"
    assert cv2 is not None
