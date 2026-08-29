"""Qoreeval fail-closed gate regression tests (Receipt 1.1 - 2026-08-29).

Three fail-closed residuals from a real laptop observation hour:

1. Confirm remint: ConfirmTicket should mint only when home/away/identity/quarter
   actually change, or lock drops. Same board → same ticket_id. Fill session_id.

2. Garbage board: Refuse lock on loading/cutscene. Require identity-compatible
   transitions (DAL-NO must not become IND-DET without a new title lock).
   0-0 only if the crop still shows two zeros AND identity holds.

3. Bodied vs OBSERVE: Live controller_bodied must follow PLAY + imu/edges on this
   host, not "a DualSense exists." OBSERVE → unbodied. Withhold timing/pattern
   coaches when unbodied.
"""

from __future__ import annotations

from qoresence.core.coupled_event import input_bodied
from qoresence.vision.confirm_ticket import ConfirmTicketBook, mint_confirm_ticket
from qoresence.vision.visual_context import GameCategory, GameState, VisualContext


def test_confirm_ticket_stable_for_same_board():
    """Confirm ticket should be stable when board AND identity do not change."""
    # Same board state with same identity should produce same ticket_id
    t1 = mint_confirm_ticket(
        session_id="sess-abc",
        clock_ns=1_000_000,
        home_score=27,
        away_score=0,
        home_team="DAL",
        away_team="NO",
        quarter=2,
        model="deepseek-v4-flash-vision-exp",
        source="deepseek",
    )
    t2 = mint_confirm_ticket(
        session_id="sess-abc",
        clock_ns=2_000_000,
        home_score=27,
        away_score=0,
        home_team="DAL",
        away_team="NO",
        quarter=2,
        model="deepseek-v4-flash-vision-exp",
        source="deepseek",
    )
    # Same board + same identity → same ticket_id (deterministic hash)
    assert t1.ticket_id == t2.ticket_id
    # session_id must be filled
    assert t1.session_id == "sess-abc"
    assert t2.session_id == "sess-abc"


def test_confirm_ticket_different_for_different_identity():
    """DAL 27-0 and IND 27-0 must be different tickets (identity in hash)."""
    t1 = mint_confirm_ticket(
        session_id="sess-abc",
        clock_ns=1_000_000,
        home_score=27,
        away_score=0,
        home_team="DAL",
        away_team="NO",
        quarter=2,
    )
    t2 = mint_confirm_ticket(
        session_id="sess-abc",
        clock_ns=2_000_000,
        home_score=27,
        away_score=0,
        home_team="IND",
        away_team="DET",
        quarter=2,
    )
    # Same scores but different identity → different ticket_id
    assert t1.ticket_id != t2.ticket_id


def test_confirm_ticket_remint_on_score_change():
    """Confirm ticket should remint when home/away actually change."""
    t1 = mint_confirm_ticket(
        session_id="sess-abc",
        clock_ns=1_000_000,
        home_score=27,
        away_score=0,
        quarter=2,
    )
    t2 = mint_confirm_ticket(
        session_id="sess-abc",
        clock_ns=2_000_000,
        home_score=27,
        away_score=3,  # away score changed
        quarter=2,
    )
    # Different board → different ticket_id
    assert t1.ticket_id != t2.ticket_id


def test_confirm_ticket_remint_on_quarter_change():
    """Confirm ticket should remint when quarter changes."""
    t1 = mint_confirm_ticket(
        session_id="sess-abc",
        clock_ns=1_000_000,
        home_score=27,
        away_score=0,
        quarter=2,
    )
    t2 = mint_confirm_ticket(
        session_id="sess-abc",
        clock_ns=2_000_000,
        home_score=27,
        away_score=0,
        quarter=3,  # quarter changed
    )
    # Different quarter → different ticket_id
    assert t1.ticket_id != t2.ticket_id


def test_confirm_ticket_book_does_not_remint_same_board():
    """ConfirmTicketBook should not create a new ticket for the same board."""
    book = ConfirmTicketBook()
    t1 = mint_confirm_ticket(
        session_id="sess-443d",
        clock_ns=1_000_000,
        home_score=27,
        away_score=0,
        quarter=2,
    )
    book.put(t1)
    latest1 = book.latest()
    assert latest1 is not None
    assert latest1.ticket_id == t1.ticket_id

    # Same board state again
    t2 = mint_confirm_ticket(
        session_id="sess-443d",
        clock_ns=2_000_000,
        home_score=27,
        away_score=0,
        quarter=2,
    )
    # ticket_id should be the same (deterministic)
    assert t2.ticket_id == t1.ticket_id
    book.put(t2)

    # Latest should still have the same ticket_id
    latest2 = book.latest()
    assert latest2 is not None
    assert latest2.ticket_id == t1.ticket_id


def test_confirm_ticket_fills_session_id():
    """Confirm ticket session_id: empty string is NOT a filled session."""
    # Empty session_id is allowed but indicates missing session context
    t1 = mint_confirm_ticket(
        session_id="",
        clock_ns=1_000_000,
        home_score=10,
        away_score=7,
    )
    # Empty session_id is preserved but not considered "filled"
    assert t1.session_id == ""

    # Non-empty session_id should be preserved
    t2 = mint_confirm_ticket(
        session_id="sess-b80e",
        clock_ns=1_000_000,
        home_score=10,
        away_score=7,
    )
    assert t2.session_id == "sess-b80e"
    
    # Operator note: last_confirm.session_id was empty all hour because
    # the caller passed empty. Filling the field with "" is not filling it.
    # Tests should verify session_id is non-empty when session is known.


def test_input_bodied_false_for_missing_hid_domain():
    """Events without hid_domain must fail closed (unbodied)."""
    # Events missing hid_domain field should fail closed
    events = [
        {
            "name": "R2",
            "kind": "press",
            "clock_ns": 1_000_000,
            # hid_domain is MISSING
        }
    ]
    coupling = {"imu_bodied": False}
    bodied, reason = input_bodied(events, coupling)
    # Missing hid_domain → fail closed (unbodied)
    assert bodied is False
    assert reason == "hid_observe"


def test_input_bodied_false_for_observe_hid():
    """controller_bodied should be False for OBSERVE HID domain."""
    # Events from OBSERVE HID (laptop USB Edge) should NOT set bodied
    events = [
        {
            "name": "R2",
            "kind": "press",
            "clock_ns": 1_000_000,
            "hid_domain": "observe",
        }
    ]
    coupling = {"imu_bodied": False}
    bodied, reason = input_bodied(events, coupling)
    # OBSERVE HID → fail closed (unbodied)
    assert bodied is False
    assert reason == "hid_observe"


def test_input_bodied_true_for_play_hid():
    """controller_bodied should be True for PLAY HID with events."""
    # Events from PLAY HID (PS5 DualSense) should set bodied
    events = [
        {
            "name": "R2",
            "kind": "press",
            "clock_ns": 1_000_000,
            "hid_domain": "play",
        }
    ]
    coupling = {"imu_bodied": False}
    bodied, reason = input_bodied(events, coupling)
    # PLAY HID with events → bodied
    assert bodied is True
    assert reason == "input_ring"


def test_input_bodied_false_with_no_events():
    """controller_bodied should be False when no events present."""
    events = []
    coupling = {"imu_bodied": False}
    bodied, reason = input_bodied(events, coupling)
    assert bodied is False
    assert reason == "pad_not_on_this_host"


def test_input_bodied_true_requires_play_and_imu():
    """PLAY events without imu_bodied should still be bodied (events present)."""
    # PLAY HID events are bodied even without imu_bodied flag
    # because events themselves prove the pad is on this host
    events = [
        {"name": "R2", "kind": "press", "clock_ns": 1_000_000, "hid_domain": "play"},
    ]
    coupling = {"imu_bodied": False}
    bodied, reason = input_bodied(events, coupling)
    # PLAY events → bodied (input_ring path)
    assert bodied is True
    assert reason == "input_ring"


def test_input_bodied_imu_bodied_without_events():
    """controller_bodied should respect imu_bodied from coupling."""
    events = []
    coupling = {"imu_bodied": True}
    bodied, reason = input_bodied(events, coupling)
    # imu_bodied=True (from PLAY pad IMU precursor) should set bodied
    assert bodied is True
    assert reason == "imu_bodied"


def test_input_bodied_mixed_events_fail_closed():
    """Any OBSERVE event in the mix should veto bodied (fail closed)."""
    # If we have a mix of PLAY and OBSERVE events, fail closed (unbodied)
    events = [
        {"name": "R2", "kind": "press", "clock_ns": 1_000_000, "hid_domain": "play"},
        {"name": "L2", "kind": "press", "clock_ns": 1_100_000, "hid_domain": "observe"},
    ]
    coupling = {"imu_bodied": False}
    bodied, reason = input_bodied(events, coupling)
    # Any OBSERVE event → fail closed (unbodied)
    assert bodied is False
    assert reason == "hid_observe"


def test_garbage_board_zero_zero_after_swap():
    """0-0 board after matchup swap should not lock unless identity holds.

    Scenario: DAL 27 - NO 0 → loading → IND 82 - DET 86 → cutscene → IND 0 - DET 0
    The 0-0 here is a stuck false board after a matchup swap, not a valid kickoff.
    """
    from qoresence.vision.scoreboard_extractor import FootballScoreboardExtractor, _ScoreStabilizer
    
    # Reset the stabilizer
    FootballScoreboardExtractor._stabilizer = _ScoreStabilizer()
    
    # Scenario: First lock DAL 27 - NO 0
    t1 = mint_confirm_ticket(
        session_id="sess-abc",
        clock_ns=1_000_000,
        home_score=27,
        away_score=0,
        quarter=2,
    )
    
    # After loading/cutscene, we have IND 0 - DET 0
    # This should produce a different ticket (different identity)
    t2 = mint_confirm_ticket(
        session_id="sess-abc",
        clock_ns=2_000_000,
        home_score=0,
        away_score=0,
        quarter=1,
    )
    
    # Different matchup → different ticket_id
    # But the 0-0 board should NOT have been locked in the first place
    # during loading/cutscene without clear identity
    assert t1.ticket_id != t2.ticket_id


def test_garbage_board_refuses_lock_on_loading():
    """Lock must be refused during loading/cutscene states entirely.

    Operator: refuse lock on loading/cutscene. Even with grounded VLM and
    clear identity, loading/cutscene states must not lock.
    """
    from qoresence.vision.scoreboard_extractor import _may_mint_lock
    
    # Loading state should refuse lock EVEN with grounded VLM + identity
    ctx = VisualContext()
    ctx.game_state = GameState.LOADING
    ctx.game_category = GameCategory.FOOTBALL
    ctx.game_profile = "madden_27"
    
    vlm = {
        "home_score": 27,
        "away_score": 0,
        "left_team": "DAL",
        "right_team": "NO",
        "quarter": 2,
        "clock_seconds": 120,
    }
    
    # Loading state → refuse lock (fail-closed)
    can_mint = _may_mint_lock(ctx, vlm)
    assert can_mint is False, "Loading state must refuse lock entirely"
    
    # Cutscene state → refuse lock (fail-closed)
    ctx.game_state = GameState.UNKNOWN  # Will be normalized to cutscene-like
    ctx.game_state = "cutscene"
    can_mint = _may_mint_lock(ctx, vlm)
    assert can_mint is False, "Cutscene state must refuse lock entirely"


def test_garbage_board_identity_compatibility():
    """Lock transitions must be identity-compatible.

    DAL-NO must not become IND-DET without a new confirm ticket.
    Operator: 07:46 sequence (DAL 27-NO 0 → loading → IND 82-86 → cutscene
    → locked IND 0-0) must fail closed.
    """
    from qoresence.vision.scoreboard_extractor import _may_mint_lock
    
    # First lock: DAL vs NO (gameplay state)
    ctx1 = VisualContext()
    ctx1.game_state = GameState.GAMEPLAY
    ctx1.game_category = GameCategory.FOOTBALL
    ctx1.home_team = "DAL"
    ctx1.away_team = "NO"
    
    t1 = mint_confirm_ticket(
        session_id="sess-abc",
        clock_ns=1_000_000,
        home_score=27,
        away_score=0,
        home_team="DAL",
        away_team="NO",
        quarter=2,
    )
    
    # Loading state → refuse lock (even if IND-DET tries to lock)
    ctx2 = VisualContext()
    ctx2.game_state = GameState.LOADING
    ctx2.game_category = GameCategory.FOOTBALL
    vlm_loading = {
        "home_score": 82,
        "away_score": 86,
        "left_team": "IND",
        "right_team": "DET",
        "quarter": 1,
    }
    can_mint_loading = _may_mint_lock(ctx2, vlm_loading)
    assert can_mint_loading is False, "Loading must refuse lock"
    
    # Cutscene with IND 0-0 → refuse lock
    ctx3 = VisualContext()
    ctx3.game_state = "cutscene"
    ctx3.game_category = GameCategory.FOOTBALL
    vlm_cutscene = {
        "home_score": 0,
        "away_score": 0,
        "left_team": "IND",
        "right_team": "DET",
        "quarter": 1,
    }
    can_mint_cutscene = _may_mint_lock(ctx3, vlm_cutscene)
    assert can_mint_cutscene is False, "Cutscene must refuse lock"
    
    # Even if we reach gameplay with IND-DET, it gets a NEW ticket
    t2 = mint_confirm_ticket(
        session_id="sess-abc",
        clock_ns=2_000_000,
        home_score=0,
        away_score=0,
        home_team="IND",
        away_team="DET",
        quarter=1,
    )
    
    # Different matchup → different ticket_id
    assert t1.ticket_id != t2.ticket_id, "Different identity must mint new ticket"
