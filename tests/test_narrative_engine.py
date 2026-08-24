"""NarrativeEngine + event-1 EventRecord — fail-closed play-by-play."""

from __future__ import annotations

from pathlib import Path

from qoresence.core.civif_tick import EventRecord
from qoresence.core.types import EventRecord as TypesEventRecord
from qoresence.foundry.narrative_engine import generate_narrative, maybe_write_after_coaches
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


def test_unlocked_raw_score_and_yard_are_not_copied():
    """Digits on unlocked ticks must not appear as situation_shift or summaries."""
    ticks = [
        {
            "clock_ns": 1_000,
            "frame_seq": 1,
            "controller_bodied": True,
            "board_locked": False,
            "clip_id": "x",
            "input_ticks": [{"button": "R2", "edge_type": "press", "clock_ns": 900}],
            "situation": {
                "board_locked": False,
                "home_score": 99,
                "away_score": 1,
                "yard_line": 5,
            },
        },
        {
            "clock_ns": 2_000,
            "frame_seq": 2,
            "controller_bodied": True,
            "board_locked": False,
            "clip_id": "x",
            "input_ticks": [],
            "situation": {
                "board_locked": False,
                "home_score": 100,
                "away_score": 1,
                "yard_line": 5,
            },
        },
    ]
    nar = generate_narrative("raw", ticks=ticks, persist=False)
    assert nar["board_locked"] is False
    assert "press_to_score" not in {e["event_type"] for e in nar["events"]}
    assert "situation_shift" not in {e["event_type"] for e in nar["events"]}
    for e in nar["events"]:
        assert e.get("situation_summary") is None
        sit = e.get("situation_summary") or {}
        assert sit.get("home_score") not in {99, 100}
        assert sit.get("yard_line") != 5
    assert "99" not in nar.get("text", "")
    assert "yl=5" not in nar.get("text", "")


def test_locked_does_not_invent_yard_or_score():
    ticks = [
        _tick(1_000, home=7, away=0, yard=None, locked=True, bodied=True),
        _tick(2_000, home=7, away=0, yard=None, locked=True, bodied=True),
    ]
    nar = generate_narrative("ny", ticks=ticks, persist=False)
    for e in nar["events"]:
        sit = e.get("situation_summary") or {}
        assert "yard_line" not in sit
        assert sit.get("yard_line") is None
        assert sit.get("home_score") != 50
        assert sit.get("yard_line") != 50


def test_bodied_unlocked_omits_press_and_spam():
    presses = [("R2", 1_000_000 + i * 10_000) for i in range(12)]
    ticks = [
        _tick(1_000_000 + i * 10_000, locked=False, bodied=True, home=0, presses=[presses[i]])
        for i in range(12)
    ]
    ticks.append(_tick(2_000_000, locked=False, bodied=True, home=7))
    nar = generate_narrative("bu", ticks=ticks, persist=False)
    types = {e["event_type"] for e in nar["events"]}
    assert "press_to_score" not in types
    assert "spam_window" not in types
    assert "situation_shift" not in types


def test_unbodied_spam_hid_names_do_not_emit_spam_window():
    ticks = []
    for i in range(12):
        t = _tick(1_000_000 + i * 10_000, bodied=False, locked=True, home=0)
        t["input_ticks"] = [{"button": "R2", "edge_type": "press", "clock_ns": 1_000_000 + i * 10_000}]
        ticks.append(t)
    nar = generate_narrative("spam", ticks=ticks, persist=False)
    types = {e["event_type"] for e in nar["events"]}
    assert "spam_window" not in types
    assert "press_to_score" not in types
    assert "R2" not in str(nar)


def test_maybe_write_after_coaches_respects_env_flag(tmp_path, monkeypatch):
    ticks = [
        _tick(1_000_000_000, home=0, yard=30, bodied=True, locked=True),
        _tick(1_050_000_000, home=7, yard=30, bodied=True, locked=True),
    ]
    dest = tmp_path / "narrative_gate.json"
    monkeypatch.delenv("QORESENCE_CIVIF_NARRATIVE_LOG", raising=False)
    maybe_write_after_coaches("gate", ticks=ticks, path=dest)
    assert not dest.exists()

    monkeypatch.setenv("QORESENCE_CIVIF_NARRATIVE_LOG", "1")
    maybe_write_after_coaches("gate", ticks=ticks, path=dest)
    assert dest.is_file()


def test_generate_narrative_persist_false_skips_file_even_when_env_on(tmp_path, monkeypatch):
    monkeypatch.setenv("QORESENCE_CIVIF_NARRATIVE_LOG", "1")
    dest = tmp_path / "narrative_skip.json"
    generate_narrative("skip", ticks=[_tick(1, locked=True)], persist=False, path=dest)
    assert not dest.exists()


def test_clip_export_and_closeout_run_narrative_after_coaches():
    coach = Path("qoresence/foundry/timing_coach.py").read_text(encoding="utf-8")
    export = coach.split("def refresh_after_clip_export")[1].split("\ndef ")[0]
    assert export.find("generate_timing_report") < export.find("generate_pattern_report")
    assert export.find("generate_pattern_report") < export.find("generate_situation_report")
    assert export.find("generate_situation_report") < export.find("maybe_write_after_coaches")
    assert export.find("maybe_write_after_coaches") < export.find("maybe_narrative")

    close = Path("qoresence/pilot/closeout.py").read_text(encoding="utf-8")
    body = close.split("def write_closeout")[1].split("\ndef ")[0]
    assert body.find("generate_timing_report") < body.find("generate_pattern_report")
    assert body.find("generate_situation_report") < body.find("maybe_write_after_coaches")
    assert body.find("maybe_write_after_coaches") < body.find("maybe_narrative")


def test_mcp_tools_list_omits_civif_narrative_and_export_clip():
    names = {t["name"] for t in TOOL_DEFS}
    assert "civif_narrative" not in names
    assert "export_clip" not in names
    assert "narrate_clip" in names
