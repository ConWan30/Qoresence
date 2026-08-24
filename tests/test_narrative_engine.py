"""NarrativeEngine + event-1 EventRecord — fail-closed play-by-play."""

from __future__ import annotations

from qoresence.core.civif_tick import EventRecord
from qoresence.core.types import EventRecord as TypesEventRecord
from qoresence.foundry.narrative_engine import generate_narrative
from qoresence.mcp.server import TOOL_DEFS


def test_event_record_schema_reexport():
    assert EventRecord is TypesEventRecord
    d = EventRecord(
        session_id="s",
        event_id="s_evt_0001",
        event_type="press_to_score",
        t_start_ns=1,
        t_end_ns=2,
        frame_start=0,
        frame_end=0,
    ).to_dict()
    assert d["schema_version"] == "event-1"
    assert "civif_narrative" not in {t["name"] for t in TOOL_DEFS}


def _tick(clock, *, bodied=True, locked=True, home=0, away=0, yard=None, presses=None, clip=""):
    return {
        "clock_ns": clock,
        "frame_seq": 1,
        "controller_bodied": bodied,
        "board_locked": locked,
        "clip_id": clip,
        "input_ticks": (
            [{"button": n, "edge_type": "press", "clock_ns": ns} for n, ns in (presses or [])]
            if bodied
            else []
        ),
        "situation": {
            "board_locked": locked,
            "home_score": home if locked else None,
            "away_score": away if locked else None,
            "yard_line": yard if locked else None,
        },
    }


def test_unbodied_omits_press_and_button_names():
    ticks = [
        _tick(1_000, bodied=False, locked=True, home=0, presses=[("R2", 1_000)]),
        _tick(2_000, bodied=False, locked=True, home=7),
    ]
    nar = generate_narrative("nb", ticks=ticks, persist=False)
    assert nar["controller_bodied"] is False
    types = {e["event_type"] for e in nar["events"]}
    assert "press_to_score" not in types
    assert "spam_window" not in types
    blob = str(nar)
    assert "R2" not in blob


def test_unlocked_omits_situation_digits():
    ticks = [
        _tick(1_000, locked=False, home=99, yard=5, presses=[("R2", 900)]),
        _tick(2_000, locked=False, home=100, yard=5),
    ]
    nar = generate_narrative("ul", ticks=ticks, persist=False)
    assert nar["board_locked"] is False
    for e in nar["events"]:
        assert e.get("situation_summary") is None
        assert e["event_type"] != "situation_shift"


def test_bodied_locked_press_to_score_and_file(tmp_path):
    ticks = [
        _tick(1_000_000_000, home=0, away=0, yard=50, clip="a"),
        _tick(1_010_000_000, home=0, away=0, yard=50, presses=[("R2", 1_000_000_000)], clip="a"),
        _tick(1_050_000_000, home=7, away=0, yard=50, clip="a"),
    ]
    dest = tmp_path / "narrative_s.json"
    nar = generate_narrative("s", ticks=ticks, persist=True, path=dest)
    types = {e["event_type"] for e in nar["events"]}
    assert "press_to_score" in types
    assert "situation_shift" in types
    pt = next(e for e in nar["events"] if e["event_type"] == "press_to_score")
    assert pt["input_summary"]["latency_ns"] == 50_000_000
    assert pt["situation_summary"]["home_score"] == 7
    assert dest.is_file()
    assert nar["schema_version"] == "narrative-1"
