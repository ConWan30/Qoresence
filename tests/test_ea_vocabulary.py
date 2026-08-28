"""Tests for ClutchBot EA vocabulary — real-time named clutch only."""

from __future__ import annotations

import pytest

from qoresence.sync.hid_seq_line import HidSeqSample, get_hid_seq_line, put_sample


def _put_hid(seq: int, buttons: tuple[str, ...]) -> None:
    put_sample(
        HidSeqSample(
            hub_seq=seq,
            hub_clock_ns=1,
            hid_clock_ns=1,
            lx=0.0,
            ly=0.0,
            r2=0.0,
            l2=0.0,
            buttons=buttons,
            hid_domain="play",
        )
    )


@pytest.fixture(autouse=True)
def _clear_hid():
    get_hid_seq_line().clear()
    yield
    get_hid_seq_line().clear()


def test_ea_vocab_unlabeled_returns_none():
    """Unlabeled verb → no dictionary words in the line."""
    from qoresence.agents.ea_vocabulary import get_ea_vocabulary_at_frame

    # No visual_context → unlabeled
    verb = get_ea_vocabulary_at_frame(
        frame_seq=100,
        clock_ns=1000000000,
        visual_context=None,
        game_profile="madden_27",
    )
    assert verb is None


def test_ea_vocab_clutch_huddle_offense_cross_snap_ball():
    """Clutch + huddle_offense + Cross → line may say Snap Ball."""
    from qoresence.agents.ea_vocabulary import enrich_clutch_line

    visual_context = {
        "game_profile": "madden_27",
        "game_state": "gameplay",
        "details": {
            "visual_phase": "huddle_offense",
        },
    }

    _put_hid(200, ("Cross",))

    base = "Clutch window opening"
    enriched = enrich_clutch_line(
        base_message=base,
        frame_seq=200,
        clock_ns=2000000000,
        visual_context=visual_context,
        game_profile="madden_27",
    )

    assert enriched == "Clutch window opening — Snap Ball"


def test_ea_vocab_cfb_l3_passing_vs_madden_r3():
    """CFB L3 passing dump vs Madden R3."""
    from qoresence.agents.ea_vocabulary import get_ea_vocabulary_at_frame

    visual_context_cfb = {
        "game_profile": "ncaa_football_27",
        "game_state": "gameplay",
        "details": {
            "visual_phase": "passing",
        },
    }
    _put_hid(300, ("L3",))

    verb_cfb = get_ea_vocabulary_at_frame(
        frame_seq=300,
        clock_ns=3000000000,
        visual_context=visual_context_cfb,
        game_profile="ncaa_football_27",
    )
    assert verb_cfb == "Throw Ball Away"

    visual_context_madden = {
        "game_profile": "madden_27",
        "game_state": "gameplay",
        "details": {
            "visual_phase": "running",
        },
    }
    _put_hid(400, ("Cross",))

    verb_madden = get_ea_vocabulary_at_frame(
        frame_seq=400,
        clock_ns=4000000000,
        visual_context=visual_context_madden,
        game_profile="madden_27",
    )
    assert verb_madden == "Stiff Arm"
    assert verb_madden != "Throw Ball Away"


def test_ea_vocab_non_clutch_cross_no_enrich():
    """Non-clutch Cross → no speak (base message unchanged)."""
    from qoresence.agents.ea_vocabulary import enrich_clutch_line

    # No visual_context → unlabeled → no enrichment
    base = "Input spike"
    enriched = enrich_clutch_line(
        base_message=base,
        frame_seq=500,
        clock_ns=5000000000,
        visual_context=None,
        game_profile="madden_27",
    )
    assert enriched == base  # Unchanged


def test_ea_vocab_phrase_strings_stay_gone():
    """Phrase strings (IDLE/HUDDLE/SPRINT) stay gone from vocab."""
    from qoresence.agents.ea_vocabulary import get_ea_vocabulary_at_frame

    # EA vocab only returns verbs (Snap Ball, Stiff Arm, etc.)
    # Never returns Phrase strings (IDLE, HUDDLE, SPRINT)
    visual_context = {
        "game_profile": "madden_27",
        "game_state": "gameplay",
        "details": {
            "visual_phase": "huddle_offense",
        },
    }

    _put_hid(600, ("Cross",))

    verb = get_ea_vocabulary_at_frame(
        frame_seq=600,
        clock_ns=6000000000,
        visual_context=visual_context,
        game_profile="madden_27",
    )

    # EA verb is "Snap Ball", not "HUDDLE" or "SNAP"
    assert verb == "Snap Ball"
    assert verb not in {"IDLE", "HUDDLE", "SNAP", "SPRINT", "CUT", "RELEASE"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
