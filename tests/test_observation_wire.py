"""Tests for observation wire — LAYER A spine isomorphism."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from qoresence.sync.hid_seq_line import HidSeqSample, get_hid_seq_line, put_sample
from qoresence.sync.picture_hid_book import reset_picture_hid_book
from qoresence.vision.picture_hid_ticket import mint_picture_hid_ticket


def _hid_sample(seq: int, buttons: tuple[str, ...], domain: str | None = "observe", clock_ns: int = 1) -> None:
    get_hid_seq_line().clear()
    put_sample(
        HidSeqSample(
            hub_seq=seq,
            hub_clock_ns=clock_ns,
            hid_clock_ns=clock_ns,
            lx=0.0,
            ly=0.0,
            r2=0.0,
            l2=0.0,
            buttons=buttons,
            hid_domain=domain,
        )
    )


@pytest.fixture(autouse=True)
def _reset_lines():
    get_hid_seq_line().clear()
    reset_picture_hid_book()
    yield
    get_hid_seq_line().clear()
    reset_picture_hid_book()


def test_observation_wire_unlabeled_when_no_visual_phase():
    """Unlabeled when no visual_phase (honest empty state)."""
    from qoresence.deck.observation_wire import build_observation_wire

    situation = {
        "frame_seq": 100,
        "clock_ns": 1000000000,
        "game_profile": "madden_27",
    }
    _hid_sample(100, ("Cross",), clock_ns=1000000000)

    obs = build_observation_wire(situation)
    assert obs is not None
    assert obs["frame_seq"] == 100
    assert obs["hid_button"] == "Cross"
    assert obs["verb"] is None
    assert obs["mode"] is None
    assert obs["visual_phase"] is None
    assert obs["conflict"] is None
    assert obs["hid_source"] == "usb_observe"


def test_observation_wire_snap_ball_on_cross_huddle_offense():
    """Cross + huddle_offense → Snap Ball (preplay_offense)."""
    from qoresence.deck.observation_wire import build_observation_wire
    from qoresence.vision.visual_context import VisualContext

    visual_context = VisualContext(
        game_profile="madden_27",
        game_state="gameplay",
        game_title="Madden NFL 27",
        details={"visual_phase": "huddle_offense"},
    )

    situation = {
        "frame_seq": 200,
        "clock_ns": 2000000000,
        "game_profile": "madden_27",
    }
    _hid_sample(200, ("Cross",), domain="play", clock_ns=2000000000)

    with patch("qoresence.lobes.visual.get_last_visual_context") as mock_get:
        mock_get.return_value = visual_context
        obs = build_observation_wire(situation)

    assert obs is not None
    assert obs["hid_button"] == "Cross"
    assert obs["verb"] == "Snap Ball"
    assert obs["mode"] == "preplay_offense"
    assert obs["visual_phase"] == "huddle_offense"
    assert obs["hid_source"] == "usb_play"
    assert obs["conflict"] is None


def test_observation_wire_cfb_l3_passing():
    """CFB L3 in passing → Throw Ball Away."""
    from qoresence.deck.observation_wire import build_observation_wire
    from qoresence.vision.visual_context import VisualContext

    visual_context = VisualContext(
        game_profile="ncaa_football_27",
        game_state="gameplay",
        game_title="NCAA College Football 27",
        details={"visual_phase": "passing"},
    )

    situation = {
        "frame_seq": 300,
        "clock_ns": 3000000000,
        "game_profile": "ncaa_football_27",
    }
    _hid_sample(300, ("L3",), domain="play", clock_ns=3000000000)

    with patch("qoresence.lobes.visual.get_last_visual_context") as mock_get:
        mock_get.return_value = visual_context
        obs = build_observation_wire(situation)

    assert obs is not None
    assert obs["hid_button"] == "L3"
    assert obs["verb"] == "Throw Ball Away"
    assert obs["mode"] == "passing"
    assert obs["visual_phase"] == "passing"


def test_observation_wire_none_when_no_hid_sample():
    """Returns None when no HID sample and no picture ticket at frame_seq."""
    from qoresence.deck.observation_wire import build_observation_wire

    situation = {
        "frame_seq": 999,
        "clock_ns": 9000000000,
        "game_profile": "madden_27",
    }
    obs = build_observation_wire(situation)
    assert obs is None


def test_observation_wire_picture_ticket_when_usb_empty():
    from qoresence.deck.observation_wire import build_observation_wire
    from qoresence.sync.picture_hid_book import get_picture_hid_book

    t = mint_picture_hid_ticket(
        clock_ns=1,
        frame_seq=50,
        hid_button="Cross",
        source="gemini",
        verb="Snap Ball",
        mode="preplay_offense",
        visual_phase="huddle_offense",
        game_profile="madden_27",
    )
    get_picture_hid_book().put(t)
    obs = build_observation_wire(
        {"frame_seq": 50, "clock_ns": 1, "game_profile": "madden_27"}
    )
    assert obs is not None
    assert obs["hid_button"] == "Cross"
    assert obs["hid_source"] == "picture"
    assert obs["verb"] == "Snap Ball"
    assert obs["mode"] == "preplay_offense"


def test_observation_wire_hid_mismatch_no_silent_overwrite():
    from qoresence.deck.observation_wire import build_observation_wire
    from qoresence.sync.picture_hid_book import get_picture_hid_book

    _hid_sample(8, ("Cross",), domain="observe")
    t = mint_picture_hid_ticket(
        clock_ns=1,
        frame_seq=8,
        hid_button="Triangle",
        source="gemini",
    )
    get_picture_hid_book().put(t)
    obs = build_observation_wire({"frame_seq": 8, "clock_ns": 1, "game_profile": "madden_27"})
    assert obs is not None
    assert obs["hid_button"] == "Cross"
    assert obs["hid_source"] == "usb_observe"
    assert obs["conflict"] is not None
    assert obs["conflict"]["kind"] == "hid_mismatch"
    assert obs["conflict"]["picture_sheet"] == "Triangle"
    assert obs["conflict"]["pad_sheet"] == "Cross"


def test_observation_wire_unlabeled_cross_with_unknown_profile():
    """Unlabeled Cross when profile unknown: hid_button present, verb/mode None."""
    from qoresence.deck.observation_wire import build_observation_wire

    situation = {
        "frame_seq": 400,
        "clock_ns": 4000000000,
    }
    _hid_sample(400, ("Cross",), clock_ns=4000000000)

    with patch("qoresence.lobes.visual.get_last_visual_context") as mock_get:
        mock_get.return_value = None
        obs = build_observation_wire(situation)

    assert obs is not None
    assert obs["hid_button"] == "Cross"
    assert obs["verb"] is None
    assert obs["mode"] is None
    assert obs["visual_phase"] is None
    assert obs["game_profile"] is None
    assert obs["conflict"] is None


def test_observation_wire_visual_context_dataclass_instance():
    """VisualContext dataclass instance (not dict) still emits unlabeled HID."""
    from qoresence.deck.observation_wire import build_observation_wire
    from qoresence.vision.visual_context import VisualContext

    visual_context = VisualContext(
        game_profile="madden_27",
        game_state="gameplay",
        game_title="Madden NFL 27",
    )

    situation = {
        "frame_seq": 500,
        "clock_ns": 5000000000,
        "game_profile": "madden_27",
    }
    _hid_sample(500, ("Triangle",), clock_ns=5000000000)

    with patch("qoresence.lobes.visual.get_last_visual_context") as mock_get:
        mock_get.return_value = visual_context
        obs = build_observation_wire(situation)

    assert obs is not None
    assert obs["hid_button"] == "Triangle"
    assert obs["verb"] is None
    assert obs["mode"] is None
    assert obs["visual_phase"] is None
    assert obs["game_profile"] == "madden_27"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
