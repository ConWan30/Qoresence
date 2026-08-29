"""Qoreeval Receipt 1.1 residuals — remint, garbage board, OBSERVE bodied."""

from __future__ import annotations

from qoresence.core.civif_tick import build_coupled_tick
from qoresence.core.coupled_event import input_bodied, validate_coupling
from qoresence.core.session import SessionAuthority
from qoresence.sync.hid_domain import HidDomain, allow_imu_bodied
from qoresence.vision.confirm_ticket import (
    ConfirmTicketBook,
    get_ticket_book,
    mint_confirm_ticket,
    resolve_session_id,
)
from qoresence.vision.scoreboard_extractor import (
    _ScoreStabilizer,
    _may_mint_lock,
    garbage_lock_reason,
)
from qoresence.vision.visual_context import VisualContext


def setup_function() -> None:
    get_ticket_book().clear()
    SessionAuthority.clear()


def test_confirm_ticket_reuses_id_on_the_book_mint_reads():
    """Remint must use the same book put() writes. Local-only books are a lie."""
    book = ConfirmTicketBook()
    t1 = mint_confirm_ticket(
        session_id="sess-1",
        clock_ns=1_000_000_000,
        home_score=27,
        away_score=0,
        quarter=1,
        home_team="DAL",
        away_team="NO",
        book=book,
    )
    book.put(t1, home_team="DAL", away_team="NO")
    t2 = mint_confirm_ticket(
        session_id="sess-1",
        clock_ns=2_000_000_000,
        home_score=27,
        away_score=0,
        quarter=1,
        home_team="DAL",
        away_team="NO",
        book=book,
    )
    assert t2.ticket_id == t1.ticket_id
    t3 = mint_confirm_ticket(
        session_id="sess-1",
        clock_ns=3_000_000_000,
        home_score=34,
        away_score=0,
        quarter=1,
        home_team="DAL",
        away_team="NO",
        book=book,
    )
    assert t3.ticket_id != t1.ticket_id
    book.put(t3, home_team="DAL", away_team="NO")
    t4 = mint_confirm_ticket(
        session_id="sess-1",
        clock_ns=4_000_000_000,
        home_score=34,
        away_score=0,
        quarter=1,
        home_team="IND",
        away_team="DET",
        book=book,
    )
    assert t4.ticket_id != t3.ticket_id


def test_confirm_ticket_global_book_is_the_live_path():
    """Extractor calls get_ticket_book().put — remint must hit that book."""
    book = get_ticket_book()
    t1 = mint_confirm_ticket(
        session_id="sess-live",
        clock_ns=1,
        home_score=21,
        away_score=14,
        quarter=3,
        home_team="IND",
        away_team="DET",
    )
    book.put(t1, home_team="IND", away_team="DET")
    t2 = mint_confirm_ticket(
        session_id="sess-live",
        clock_ns=2,
        home_score=21,
        away_score=14,
        quarter=3,
        home_team="IND",
        away_team="DET",
    )
    assert t2.ticket_id == t1.ticket_id
    t3 = mint_confirm_ticket(
        session_id="sess-live",
        clock_ns=3,
        home_score=21,
        away_score=14,
        quarter=4,
        home_team="IND",
        away_team="DET",
    )
    assert t3.ticket_id == t1.ticket_id, "quarter flicker must not remint"


def test_confirm_ticket_fills_session_id_from_authority():
    SessionAuthority.mint(session_id="sess-from-authority")
    t = mint_confirm_ticket(
        session_id="",
        clock_ns=1,
        home_score=17,
        away_score=0,
        home_team="DAL",
        away_team="NO",
        book=ConfirmTicketBook(),
    )
    assert t.session_id == "sess-from-authority"
    assert resolve_session_id("") == "sess-from-authority"
    assert resolve_session_id("explicit") == "explicit"


def test_confirm_ticket_reuses_id_across_wordmark_flicker():
    """Receipt 2: DAL / Dallas / Cowboys / empty must not remint the same board."""
    book = ConfirmTicketBook()
    t1 = mint_confirm_ticket(
        session_id="s",
        clock_ns=1,
        home_score=21,
        away_score=13,
        quarter=4,
        home_team="DAL",
        away_team="NO",
        book=book,
    )
    book.put(t1, home_team="DAL", away_team="NO")
    t2 = mint_confirm_ticket(
        session_id="s",
        clock_ns=2,
        home_score=21,
        away_score=13,
        quarter=4,
        home_team="Dallas Cowboys",
        away_team="New Orleans Saints",
        book=book,
    )
    assert t2.ticket_id == t1.ticket_id
    book.put(t2, home_team="Dallas Cowboys", away_team="New Orleans Saints")
    t3 = mint_confirm_ticket(
        session_id="s",
        clock_ns=3,
        home_score=21,
        away_score=13,
        quarter=4,
        home_team="Cowboys",
        away_team="Saints",
        book=book,
    )
    assert t3.ticket_id == t1.ticket_id
    book.put(t3, home_team="Cowboys", away_team="Saints")
    t4 = mint_confirm_ticket(
        session_id="s",
        clock_ns=4,
        home_score=21,
        away_score=13,
        quarter=4,
        home_team="",
        away_team="",
        book=book,
    )
    assert t4.ticket_id == t1.ticket_id


def test_confirm_ticket_empty_then_named_reuses_id():
    """First lock with empty teams, then DAL–NO at the same score, is not a remint."""
    book = ConfirmTicketBook()
    t1 = mint_confirm_ticket(
        session_id="s",
        clock_ns=1,
        home_score=0,
        away_score=0,
        quarter=1,
        home_team="",
        away_team="",
        book=book,
    )
    book.put(t1, home_team="", away_team="")
    t2 = mint_confirm_ticket(
        session_id="s",
        clock_ns=2,
        home_score=0,
        away_score=0,
        quarter=1,
        home_team="DAL",
        away_team="NO",
        book=book,
    )
    assert t2.ticket_id == t1.ticket_id


def test_confirm_ticket_remint_reduces_churn():
    book = ConfirmTicketBook()
    ids = []
    for i in range(10):
        t = mint_confirm_ticket(
            session_id="sess",
            clock_ns=(i + 1) * 1_000_000_000,
            home_score=21,
            away_score=14,
            quarter=3,
            home_team="IND",
            away_team="DET",
            book=book,
        )
        book.put(t, home_team="IND", away_team="DET")
        ids.append(t.ticket_id)
    assert len(set(ids)) == 1


def test_kickoff_zero_zero_is_not_suspicious():
    """Real kickoff 0-0 must be allowed. Blanket 0-0 refuse is the wrong residual."""
    assert _ScoreStabilizer._looks_suspicious_pair((0, 0)) is False
    book = ConfirmTicketBook()
    assert (
        garbage_lock_reason(
            home=0,
            away=0,
            home_team="DAL",
            away_team="NO",
            game_state="gameplay",
            book=book,
        )
        is None
    )


def test_refuse_zero_zero_after_matchup_swap():
    book = ConfirmTicketBook()
    t1 = mint_confirm_ticket(
        session_id="s",
        clock_ns=1,
        home_score=27,
        away_score=0,
        home_team="DAL",
        away_team="NO",
        book=book,
    )
    book.put(t1, home_team="DAL", away_team="NO")
    assert (
        garbage_lock_reason(
            home=0,
            away=0,
            home_team="IND",
            away_team="DET",
            game_state="gameplay",
            book=book,
        )
        == "zero_zero_after_identity_swap"
    )


def test_garbage_wordmark_flicker_is_not_identity_swap():
    book = ConfirmTicketBook()
    t1 = mint_confirm_ticket(
        session_id="s",
        clock_ns=1,
        home_score=21,
        away_score=13,
        home_team="DAL",
        away_team="NO",
        book=book,
    )
    book.put(t1, home_team="DAL", away_team="NO")
    assert (
        garbage_lock_reason(
            home=21,
            away=13,
            home_team="Dallas Cowboys",
            away_team="Saints",
            game_state="gameplay",
            book=book,
        )
        is None
    )


def test_refuse_absurd_swap_like_82_86():
    assert _ScoreStabilizer._looks_suspicious_pair((82, 86)) is True
    assert _ScoreStabilizer._plausible_transition((27, 0), (82, 86)) is False
    book = ConfirmTicketBook()
    assert (
        garbage_lock_reason(
            home=82,
            away=86,
            home_team="IND",
            away_team="DET",
            game_state="gameplay",
            book=book,
        )
        == "suspicious_pair"
    )


def test_refuse_ticker_identity_swap_9_47():
    book = ConfirmTicketBook()
    t1 = mint_confirm_ticket(
        session_id="s",
        clock_ns=1,
        home_score=3,
        away_score=31,
        home_team="IND",
        away_team="DET",
        book=book,
    )
    book.put(t1, home_team="IND", away_team="DET")
    assert (
        garbage_lock_reason(
            home=9,
            away=47,
            home_team="DAL",
            away_team="DET",
            game_state="gameplay",
            book=book,
        )
        == "identity_swap"
    )


def test_receipt_sequence_dal_loading_ind():
    """DAL 27–NO 0 → loading → IND 82–DET 86 → IND 0–DET 0 → IND 3–DET 31."""
    book = ConfirmTicketBook()
    t1 = mint_confirm_ticket(
        session_id="s",
        clock_ns=1,
        home_score=27,
        away_score=0,
        home_team="DAL",
        away_team="NO",
        book=book,
    )
    book.put(t1, home_team="DAL", away_team="NO")
    book.mark_identity_stale()
    assert (
        garbage_lock_reason(
            home=82,
            away=86,
            home_team="IND",
            away_team="DET",
            game_state="gameplay",
            book=book,
        )
        == "suspicious_pair"
    )
    assert (
        garbage_lock_reason(
            home=0,
            away=0,
            home_team="IND",
            away_team="DET",
            game_state="gameplay",
            book=book,
        )
        == "zero_zero_after_identity_swap"
    )
    assert (
        garbage_lock_reason(
            home=3,
            away=31,
            home_team="IND",
            away_team="DET",
            game_state="gameplay",
            book=book,
        )
        is None
    )


def test_refuse_lock_on_loading_cutscene():
    ctx_loading = VisualContext()
    ctx_loading.game_state = "loading"
    assert _may_mint_lock(ctx_loading, None) is False
    ctx_cutscene = VisualContext()
    ctx_cutscene.game_state = "cutscene"
    assert _may_mint_lock(ctx_cutscene, None) is False
    ctx_gameplay = VisualContext()
    ctx_gameplay.game_state = "gameplay"
    assert _may_mint_lock(ctx_gameplay, None) is True
    book = ConfirmTicketBook()
    assert (
        garbage_lock_reason(
            home=21,
            away=14,
            home_team="IND",
            away_team="DET",
            game_state="loading",
            book=book,
        )
        == "game_state"
    )


def test_observe_hid_does_not_set_imu_bodied():
    assert allow_imu_bodied(HidDomain.OBSERVE) is False
    assert allow_imu_bodied("observe") is False
    assert allow_imu_bodied(HidDomain.PLAY) is True
    assert allow_imu_bodied("play") is True


def test_observe_input_ring_does_not_set_controller_bodied():
    """Laptop USB DualSense Edge events must not set controller_bodied."""
    events = [
        {
            "clock_ns": 10,
            "name": "R2",
            "kind": "press",
            "hid_domain": "observe",
        }
    ]
    bodied, reason = input_bodied(events, {"imu_bodied": False})
    assert bodied is False
    assert reason == "hid_observe"
    rec = build_coupled_tick(
        coupling={"video_clock_ns": 10, "frame_seq": 1, "imu_bodied": False},
        events=events,
        session_id="s",
    )
    d = rec.to_dict()
    assert d["controller_bodied"] is False
    assert d["input_ticks"] == []
    assert d["input"]["events"] == []


def test_play_input_ring_sets_controller_bodied():
    events = [
        {
            "clock_ns": 10,
            "name": "R2",
            "kind": "press",
            "hid_domain": "play",
        }
    ]
    bodied, reason = input_bodied(events, {"imu_bodied": False})
    assert bodied is True
    assert reason == "input_ring"
    rec = build_coupled_tick(
        coupling={"video_clock_ns": 10, "frame_seq": 1, "imu_bodied": False},
        events=events,
        session_id="s",
    )
    assert rec.to_dict()["controller_bodied"] is True


def test_observe_sidecar_unbodied_is_valid():
    from qoresence.core.coupled_event import build_coupling_sidecar

    data = build_coupling_sidecar(
        clip_id="obs",
        session_id="s",
        start_ns=1_000,
        end_ns=2_000,
        frame_start=0,
        frame_end=1,
        video_path="obs.mp4",
        events=[{"clock_ns": 1_100, "name": "R2", "kind": "press", "hid_domain": "observe"}],
        coupling={"imu_bodied": False},
        coupling_history=[],
    )
    assert data["input"]["bodied"] is False
    assert data["input"]["reason"] == "hid_observe"
    assert validate_coupling(data) == []


def test_ivc_allow_bodied_defaults_to_false():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "qoresence" / "sync" / "ivc.py").read_text(
        encoding="utf-8"
    )
    assert "allow_bodied = False" in src
    assert "except Exception:\n                allow_bodied = False" in src.replace("\r\n", "\n")


def test_suspicious_pairs_caught():
    assert _ScoreStabilizer._looks_suspicious_pair((17, 2)) is True
    assert _ScoreStabilizer._looks_suspicious_pair((12, 2)) is True
    assert _ScoreStabilizer._looks_suspicious_pair((21, 1)) is True
    assert _ScoreStabilizer._looks_suspicious_pair((38, 1)) is True
    assert _ScoreStabilizer._looks_suspicious_pair((21, 14)) is False
    assert _ScoreStabilizer._looks_suspicious_pair((34, 27)) is False
    assert _ScoreStabilizer._looks_suspicious_pair((28, 0)) is False
    assert _ScoreStabilizer._looks_suspicious_pair((3, 31)) is False
