"""Retina Stem conductor — parity with glass director.ts."""

from __future__ import annotations

from qoresence.stem.conductor import (
    DirectorInput,
    auto_clip_allowed,
    director_brief,
    director_reasons,
    should_clip,
)

_QUIET = DirectorInput(
    now=10_000,
    hold_until=0,
    clip_busy=False,
    companion_armed=False,
    red_zone=False,
    late=False,
    close=False,
    clutch_score=0,
    clutch_kind="quiet",
    clutch_label="watching",
    clutch_why="no clutch pressure",
    companion_why="",
    clip_worth=0,
)


def test_quiet_picture_stays_on_watch():
    d = director_brief(_QUIET)
    assert d.mode == "watch"
    assert "watching" in d.why.lower()
    assert d.arm_hot is False


def test_red_zone_primes_the_next_take():
    d = director_brief(
        DirectorInput(
            **{
                **_QUIET.__dict__,
                "red_zone": True,
                "clutch_kind": "window",
                "clutch_score": 0.62,
                "clutch_label": "window",
                "clutch_why": "red zone late",
                "clip_worth": 0.7,
            }
        )
    )
    assert d.mode == "prime"
    assert "red zone" in d.why.lower()
    assert d.arm_hot is True


def test_companion_armed_beats_quiet_clutch():
    d = director_brief(
        DirectorInput(
            **{**_QUIET.__dict__, "companion_armed": True, "companion_why": "fast confirm match"}
        )
    )
    assert d.mode == "armed"
    assert "armed" in d.why.lower() or "fast confirm" in d.why.lower()


def test_hold_silences_auto_clip():
    assert auto_clip_allowed(20_000, 10_000) is False
    assert auto_clip_allowed(10_000, 10_000) is True
    d = director_brief(DirectorInput(**{**_QUIET.__dict__, "hold_until": 20_000}))
    assert d.mode == "hold"
    assert "hold" in d.why.lower()


def test_encoding_owns_the_lamp():
    d = director_brief(
        DirectorInput(
            **{
                **_QUIET.__dict__,
                "clip_busy": True,
                "hold_until": 99_000,
                "companion_armed": True,
            }
        )
    )
    assert d.mode == "encode"
    assert "encod" in d.why.lower()


def test_ticker_keeps_last_three_clip_lines():
    rows = director_reasons(
        [
            {"title": "HDMI CLIP 30s", "path": "confirm", "icon": "🎬", "at": 3},
            {"title": "chat noise", "path": "", "icon": "", "at": 2},
            {"title": "window · red zone", "path": "fast", "icon": "⚡", "at": 1},
            {"title": "older clip", "path": "confirm", "icon": "🎬", "at": 0},
            {"title": "HDMI CLIP 8s", "path": "fast", "icon": "🎬", "at": 4},
        ]
    )
    assert rows == ["HDMI CLIP 8s", "HDMI CLIP 30s", "window · red zone"]


def test_should_clip_mirrors_glass():
    assert should_clip("score_play", 0.1) is True
    assert should_clip("climax", 0.1) is True
    assert should_clip("window", 0.64) is False
    assert should_clip("window", 0.65) is True
