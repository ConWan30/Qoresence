"""Scoreboard OCR stabilizer + pair parse tests (no EasyOCR / no frames)."""

from __future__ import annotations

from qoresence.vision.scoreboard_extractor import (
    FootballScoreboardExtractor,
    _ScoreStabilizer,
)


def test_stabilizer_rejects_17_to_2_flicker():
    s = _ScoreStabilizer(window=6, need=2)
    # Lock 17-17
    assert s.update(17, 17) == (None, None)  # first sight
    assert s.update(17, 17) == (17, 17)  # consensus
    # Flaky OCR: away becomes 2
    assert s.update(17, 2) == (17, 17)  # hold
    assert s.update(17, 2) == (17, 17)  # still hold (drop not plausible)
    # Even thrice — large drop never auto-accepts without being "plausible"
    assert s.update(17, 2) == (17, 17)


def test_never_lock_in_12_2_or_17_2():
    s = _ScoreStabilizer(window=8, need=2)
    for _ in range(6):
        assert s.update(12, 2) == (None, None)
        assert s.update(17, 2) == (None, None)
    # Coherent tie can lock
    assert s.update(17, 17) == (None, None)
    assert s.update(17, 17) == (17, 17)


def test_stabilizer_accepts_real_score_increase():
    s = _ScoreStabilizer(window=6, need=2)
    s.update(17, 17)
    s.update(17, 17)
    assert s.update(17, 17) == (17, 17)
    # TD + XP → 24
    assert s.update(24, 17) == (17, 17)  # first sight of change
    assert s.update(24, 17) == (24, 17)  # consensus


def test_find_score_pair_text():
    from qoresence.vision.scoreboard_extractor import _Cluster

    clusters = [
        _Cluster(text="HOME", x=0.2, y=0.4, conf=0.9),
        _Cluster(text="17-17", x=0.5, y=0.4, conf=0.95),
        _Cluster(text="AWAY", x=0.8, y=0.4, conf=0.9),
    ]
    pair = FootballScoreboardExtractor._find_score_pair_text(clusters)
    assert pair == (17, 17)


def test_parse_int_pure_digits_unchanged():
    assert FootballScoreboardExtractor._parse_int("17") == 17
    assert FootballScoreboardExtractor._parse_int("2") == 2


def test_parse_prefers_multi_digit_pair_31_38():
    """Synthetic clusters: left 31, right 38, center noise 2 (quarter)."""
    from qoresence.vision.scoreboard_extractor import _Token

    tokens = [
        _Token(text="31", x=0.22, y=0.45, conf=0.95),
        _Token(text="2", x=0.50, y=0.45, conf=0.90),  # quarter leak
        _Token(text="38", x=0.78, y=0.45, conf=0.94),
        _Token(text="HOME", x=0.15, y=0.45, conf=0.8),
        _Token(text="AWAY", x=0.85, y=0.45, conf=0.8),
    ]
    ext = FootballScoreboardExtractor()
    parsed = ext._parse(tokens)
    assert parsed.get("home_score") == 31
    assert parsed.get("away_score") == 38
