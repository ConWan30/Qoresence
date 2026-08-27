"""Tests for ClutchBot EA vocabulary — real-time named clutch only."""

from __future__ import annotations

import pytest


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
    from unittest.mock import Mock, patch

    visual_context = {
        "game_profile": "madden_27",
        "game_state": "gameplay",
        "details": {
            "visual_phase": "huddle_offense",
        },
    }

    # Mock hid_by_seq
    from qoresence.sync.hid_seq_line import HidSeqSample, put_sample

    sample = HidSeqSample(
        frame_seq=200,
        clock_ns=2000000000,
        buttons=("Cross",),
        hold_energy=0.5,
        edge_energy=0.5,
    )
    put_sample(sample)

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
    from qoresence.sync.hid_seq_line import HidSeqSample, put_sample

    # CFB L3 in passing → Throw Ball Away
    visual_context_cfb = {
        "game_profile": "ncaa_football_27",
        "game_state": "gameplay",
        "details": {
            "visual_phase": "passing",
        },
    }

    sample_cfb = HidSeqSample(
        frame_seq=300,
        clock_ns=3000000000,
        buttons=("L3",),
        hold_energy=0.5,
        edge_energy=0.5,
    )
    put_sample(sample_cfb)

    verb_cfb = get_ea_vocabulary_at_frame(
        frame_seq=300,
        clock_ns=3000000000,
        visual_context=visual_context_cfb,
        game_profile="ncaa_football_27",
    )
    assert verb_cfb == "Throw Ball Away"

    # Madden R3 in running → different verb
    visual_context_madden = {
        "game_profile": "madden_27",
        "game_state": "gameplay",
        "details": {
            "visual_phase": "running",
        },
    }

    sample_madden = HidSeqSample(
        frame_seq=400,
        clock_ns=4000000000,
        buttons=("R3",),
        hold_energy=0.5,
        edge_energy=0.5,
    )
    put_sample(sample_madden)

    verb_madden = get_ea_vocabulary_at_frame(
        frame_seq=400,
        clock_ns=4000000000,
        visual_context=visual_context_madden,
        game_profile="madden_27",
    )
    # R3 in Madden running → Dive (or other Madden-specific verb)
    assert verb_madden is not None
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

    from qoresence.sync.hid_seq_line import HidSeqSample, put_sample

    sample = HidSeqSample(
        frame_seq=600,
        clock_ns=6000000000,
        buttons=("Cross",),
        hold_energy=0.5,
        edge_energy=0.5,
    )
    put_sample(sample)

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
