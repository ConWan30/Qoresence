"""Score-transition plausibility — veto-only, never a license."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from qoresence.core import RetinaEventBus
from qoresence.observability.score_plausibility import (
    ScorePlausibility,
    compose_verdict,
    jev_flags_transition,
    last_refused,
    local_plausibility,
    make_plausibility_from_config,
    note_refused,
    reset_score_plausibility,
)
from qoresence.sync.digit_integrity import (
    digit_void_reason,
    implausible_transition_reason,
)
from qoresence.sync.seqgate import NULL_DIGIT, license_digits
from qoresence.vision.board_why import refuse_to_board_why
from qoresence.vision.scoreboard_extractor import garbage_lock_reason

@pytest.fixture(autouse=True)
def _clean_slots():
    reset_score_plausibility()
    yield
    reset_score_plausibility()


LICENSED = {
    "confirm_ticket_id": "c-1",
    "score_vlm_locked": True,
    "path": "confirm",
    "ticket_crop_hash": "crop-a",
    "live_crop_hash": "crop-a",
    "same_seq": True,
    "ticket_clock_ns": 1_000,
    "live_clock_ns": 2_000,
    "frame_seq": 42,
    "home_score": 20,
    "away_score": 0,
}


class _IdentBook:
    def __init__(self, home: int, away: int, ht: str = "LOU", at: str = "NCST") -> None:
        self._ident = (home, away, ht, at)
        self._stale = False

    def last_board_identity(self):
        return self._ident

    def identity_stale(self) -> bool:
        return self._stale


def test_legal_increments_are_not_vetoed():
    for dh in (1, 2, 3, 6, 7, 8):
        assert implausible_transition_reason(7, 3, 7 + dh, 3) is None
        assert implausible_transition_reason(7, 3, 7, 3 + dh) is None
    assert implausible_transition_reason(7, 3, 7, 3) is None


def test_ocr_echo_20_0_to_20_20_is_vetoed():
    assert implausible_transition_reason(20, 0, 20, 20) == "implausible_transition"


def test_drop_and_both_sides_are_vetoed():
    assert implausible_transition_reason(14, 7, 7, 7) == "implausible_transition"
    assert implausible_transition_reason(14, 7, 17, 10) == "implausible_transition"


def test_missing_prior_is_not_a_veto():
    assert implausible_transition_reason(None, None, 20, 20) is None
    assert implausible_transition_reason(7, 0, None, 3) is None


def test_garbage_lock_refuses_ocr_echo_on_same_identity():
    book = _IdentBook(20, 0)
    assert (
        garbage_lock_reason(
            home=20,
            away=20,
            home_team="LOU",
            away_team="NCST",
            game_state="gameplay",
            book=book,
            crop_hash="abc",
        )
        == "implausible_transition"
    )


def test_legal_fg_still_mints_on_same_identity():
    book = _IdentBook(7, 3)
    assert (
        garbage_lock_reason(
            home=10,
            away=3,
            home_team="LOU",
            away_team="NCST",
            game_state="gameplay",
            book=book,
            crop_hash="abc",
        )
        is None
    )


def test_identity_swap_still_beats_plausibility():
    book = _IdentBook(20, 0, "LOU", "NCST")
    assert (
        garbage_lock_reason(
            home=20,
            away=20,
            home_team="DAL",
            away_team="DET",
            game_state="gameplay",
            book=book,
            crop_hash="abc",
        )
        == "identity_swap"
    )


def test_seqgate_implausible_is_null_digit_veto():
    gate = license_digits(**{**LICENSED, "implausible": True})
    assert gate["licensed"] is False
    assert gate["speech"] == NULL_DIGIT
    assert gate["reason"] == "implausible_transition"
    assert gate["bind"]["kind"] == "veto"
    assert gate["layer"] == "plausibility"
    assert "20" not in gate["speech"]


def test_seqgate_implausible_cannot_talk_a_licensed_ticket_into_digits():
    """Even a fully licensed ticket bag is blanked by the plausibility veto."""
    reason = digit_void_reason(
        confirm_ticket_id="c-1",
        score_vlm_locked=True,
        path="confirm",
        ticket_crop_hash="crop-a",
        live_crop_hash="crop-a",
        same_seq=True,
        ticket_clock_ns=1_000,
        live_clock_ns=2_000,
        implausible=True,
    )
    assert reason == "implausible_transition"


def test_board_why_maps_implausible():
    assert refuse_to_board_why("implausible_transition") == "refuse_implausible"


def test_compose_verdict_high_noul_flags_veto_never_licenses():
    v = compose_verdict(implausible_noul=0.85, jump_kind="ocr_echo")
    assert v["action"] == "flag_veto"
    assert v["licenses_digits"] is False


def test_compose_verdict_coin_flip_observes():
    v = compose_verdict(implausible_noul=0.5)
    assert v["action"] == "watch"
    assert v["licenses_digits"] is False
    v2 = compose_verdict(implausible_noul=0.2)
    assert v2["action"] == "observe"


def test_compose_verdict_local_reason_forces_veto_even_on_low_noul():
    v = compose_verdict(
        implausible_noul=0.2,
        local_reason="implausible_transition",
    )
    assert v["action"] == "flag_veto"


def test_local_plausibility_flags_ocr_echo():
    out = local_plausibility(
        {
            "prior": {"home_score": 20, "away_score": 0},
            "proposed": {"home_score": 20, "away_score": 20},
        }
    )
    assert out["local_reason"] == "implausible_transition"
    assert out["implausible_noul"] >= 0.7
    assert out["jump_kind"] == "ocr_echo"
    assert out["source"] == "local_heuristic"


def test_local_plausibility_legal_fg():
    out = local_plausibility(
        {
            "prior": {"home_score": 7, "away_score": 3},
            "proposed": {"home_score": 10, "away_score": 3},
        }
    )
    assert out["local_reason"] is None
    assert out["jump_kind"] == "legal_score"
    assert out["implausible_noul"] < 0.4


def test_disabled_by_default():
    assert make_plausibility_from_config(SimpleNamespace(enabled=False)) is None


def test_worker_never_emits_bus_events(tmp_path):
    bus = RetinaEventBus(
        session_id="t", jsonl_path=tmp_path / "e.jsonl", enable_ws=False
    )
    captured: list = []
    bus.subscribe(captured.append)
    note_refused(
        prior_home=20, prior_away=0, home=20, away=20, reason="implausible_transition"
    )
    cfg = SimpleNamespace(enabled=True, cadence_s=0.05, out_dir=str(tmp_path))
    sp = ScorePlausibility(cfg, bus=bus)
    try:
        snap = sp._collect()
        verdict = sp._judge(snap)
        sp._write_jsonl(verdict)
        time.sleep(0.15)
    finally:
        sp.stop()
        bus.close()
    assert captured == []
    assert verdict["licenses_digits"] is False
    assert verdict["action"] == "flag_veto"
    rows = (tmp_path / "score_plausibility.jsonl").read_text(
        encoding="utf-8"
    ).strip().splitlines()
    assert rows
    last = json.loads(rows[-1])
    assert last["licenses_digits"] is False
    assert last["action"] == "flag_veto"


def test_jev_flag_cannot_grant_a_legal_increment():
    """A leftover veto key must not fire on a different (legal) pair."""
    note_refused(
        prior_home=20, prior_away=0, home=20, away=20, reason="implausible_transition"
    )
    assert jev_flags_transition(7, 3, 10, 3) is False


def test_note_refused_slot_newest_wins():
    note_refused(prior_home=7, prior_away=0, home=14, away=0, reason="other")
    note_refused(
        prior_home=20, prior_away=0, home=20, away=20, reason="implausible_transition"
    )
    snap = last_refused()
    assert snap is not None
    assert snap["proposed"]["away_score"] == 20
    assert snap["reason"] == "implausible_transition"
