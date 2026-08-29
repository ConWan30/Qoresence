"""PictureHidTicket contract — seeing-path only, no bind, seq-keyed book."""

from __future__ import annotations

import pytest

from qoresence.sync.hid_domain import (
    HidDomain,
    allow_bind,
    allow_coupling_ticket,
    allow_imu_bodied,
    allow_pll_observe_phase,
)
from qoresence.sync.picture_hid_book import get_picture_hid_book, reset_picture_hid_book
from qoresence.vision.picture_hid_ticket import (
    PictureHidTicketError,
    PictureHidTicketSourceError,
    is_picture_hid_source,
    mint_picture_hid_ticket,
    try_mint_picture_hid_from_context,
)


@pytest.fixture(autouse=True)
def _reset_book():
    reset_picture_hid_book()
    yield
    reset_picture_hid_book()


def test_mint_with_local_hud_raises():
    with pytest.raises(PictureHidTicketSourceError, match="local_hud"):
        mint_picture_hid_ticket(
            clock_ns=1,
            frame_seq=1,
            hid_button="Cross",
            source="local_hud",
        )


def test_mint_with_chrome_raises():
    with pytest.raises(PictureHidTicketSourceError, match="seeing-path"):
        mint_picture_hid_ticket(
            clock_ns=1,
            frame_seq=1,
            hid_button="Cross",
            source="chrome",
        )


def test_mint_with_easyocr_scorebug_raises():
    """Score OCR is not a control-glyph seeing path."""
    with pytest.raises(PictureHidTicketSourceError):
        mint_picture_hid_ticket(
            clock_ns=1,
            frame_seq=1,
            hid_button="Cross",
            source="easyocr_scorebug",
        )


def test_mint_with_gemini_succeeds():
    t = mint_picture_hid_ticket(
        clock_ns=100,
        frame_seq=42,
        hid_button="Cross",
        source="gemini",
    )
    assert t.source == "gemini"
    assert t.hid_button == "Cross"
    assert t.frame_seq == 42
    assert t.hid_domain == "picture"


def test_mint_with_quicksilver_alias():
    t = mint_picture_hid_ticket(
        clock_ns=1,
        frame_seq=2,
        hid_button="Circle",
        source="qs",
    )
    assert t.source == "quicksilver"


def test_mint_refuses_analog_left_stick():
    with pytest.raises(PictureHidTicketError):
        mint_picture_hid_ticket(
            clock_ns=1,
            frame_seq=1,
            hid_button="Left Stick",
            source="gemini",
        )


def test_mint_refuses_chord():
    with pytest.raises(PictureHidTicketError):
        mint_picture_hid_ticket(
            clock_ns=1,
            frame_seq=1,
            hid_button="Cross + Left Stick",
            source="gemini",
        )


def test_mint_refuses_menu_state():
    with pytest.raises(PictureHidTicketError, match="game_state"):
        mint_picture_hid_ticket(
            clock_ns=1,
            frame_seq=1,
            hid_button="Cross",
            source="gemini",
            game_state="paused",
        )


def test_mint_refuses_missing_button():
    with pytest.raises(PictureHidTicketError):
        mint_picture_hid_ticket(
            clock_ns=1,
            frame_seq=1,
            hid_button=None,
            source="gemini",
        )


def test_picture_domain_vetoes_bind():
    assert not allow_bind(HidDomain.PICTURE)
    assert not allow_bind("picture")
    assert not allow_coupling_ticket("picture")
    assert not allow_pll_observe_phase("picture")
    assert not allow_imu_bodied("picture")
    assert allow_bind(HidDomain.PLAY)


def test_is_picture_hid_source():
    assert is_picture_hid_source("gemini") is True
    assert is_picture_hid_source("quicksilver") is True
    assert is_picture_hid_source("easyocr_scorebug") is False
    assert is_picture_hid_source("local_hud") is False
    assert is_picture_hid_source(None) is False


def test_book_exact_seq_fail_closed():
    t = mint_picture_hid_ticket(
        clock_ns=1,
        frame_seq=10,
        hid_button="Triangle",
        source="gemini",
    )
    book = get_picture_hid_book()
    book.put(t)
    assert book.latest_live(10) is t
    assert book.latest_live(11) is None
    assert book.get(None) is None
    assert book.latest_nearby(10) is t
    assert book.latest_nearby(40) is t
    assert book.latest_nearby(101) is None
    assert book.latest_nearby(9) is None


def test_try_mint_from_context_puts_book():
    from qoresence.vision.visual_context import GameCategory, GameState, VisualContext

    ctx = VisualContext(
        game_state=GameState.GAMEPLAY,
        game_profile="madden_27",
        game_category=GameCategory.FOOTBALL,
        details={"visual_phase": "huddle_offense"},
        visible_control={"button": "Cross", "glyph": "✕", "prompt": "Snap"},
    )
    t = try_mint_picture_hid_from_context(ctx, frame_seq=7, clock_ns=99, source="gemini")
    assert t is not None
    assert t.hid_button == "Cross"
    assert t.verb == "Snap Ball"
    assert t.mode == "preplay_offense"
    assert get_picture_hid_book().latest_live(7) is t


def test_try_mint_null_visible_control():
    from qoresence.vision.visual_context import GameState, VisualContext

    ctx = VisualContext(
        game_state=GameState.GAMEPLAY,
        visible_control={"button": None, "glyph": None, "prompt": None},
    )
    assert try_mint_picture_hid_from_context(ctx, frame_seq=1, clock_ns=1) is None


def test_try_mint_does_not_infer_from_visual_phase_alone():
    from qoresence.vision.visual_context import GameState, VisualContext

    ctx = VisualContext(
        game_state=GameState.GAMEPLAY,
        game_profile="madden_27",
        details={"visual_phase": "snap"},
    )
    assert try_mint_picture_hid_from_context(ctx, frame_seq=1, clock_ns=1) is None


def test_from_dict_parses_visible_control():
    from qoresence.vision.visual_context import VisualContext, build_football_prompt

    ctx = VisualContext.from_dict(
        {
            "game_state": "gameplay",
            "game_category": "football",
            "visible_control": {"button": "Cross", "glyph": "✕", "prompt": "Snap"},
        }
    )
    assert ctx.visible_control is not None
    assert ctx.visible_control["button"] == "Cross"
    assert "visible_control" in build_football_prompt()
