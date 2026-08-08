"""Tests for Phase 5.1: Richer football event vocabulary.

Verifies that the outcome lobe emits touchdown, field_goal, safety,
two_point_conversion, red_zone_entry, and two_minute_warning events
with correct inference logic.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from qoresence.core import (
    EventType,
    GameProfileId,
    OutcomeConfig,
    RetinaEventBus,
    SessionAuthority,
    SourceLobe,
)
from qoresence.core.unified_config import NCAA_FOOTBALL_27_PROFILE
from qoresence.lobes.outcome import OutcomeRuntime
from qoresence.vision.visual_context import GameCategory, GameState, VisualContext


def _make_ctx(
    *,
    home_score: int | None = 0,
    away_score: int | None = 0,
    quarter: int | None = 1,
    down: int | None = 1,
    yards_to_go: int | None = 10,
    possession: str | None = "home",
    field_position: str | None = "own 25",
    play_clock: int | None = 25,
    clock_seconds: int | None = 600,
    confidence: float = 0.9,
) -> VisualContext:
    return VisualContext(
        game_category=GameCategory.FOOTBALL,
        game_state=GameState.GAMEPLAY,
        home_score=home_score,
        away_score=away_score,
        quarter=quarter,
        down=down,
        yards_to_go=yards_to_go,
        possession=possession,
        field_position=field_position,
        play_clock=play_clock,
        clock_seconds=clock_seconds,
        confidence=confidence,
    )


def _setup(tmpdir: Path):
    """Create outcome runtime + bus, emit GAME_DETECTED, return (rt, bus, identity)."""
    jsonl_path = tmpdir / "events.jsonl"
    bus = RetinaEventBus(session_id="test", jsonl_path=jsonl_path, enable_ws=False)
    identity = SessionAuthority.mint(session_id="test")
    config = OutcomeConfig(
        enabled=True,
        game_profile=GameProfileId.NCAA_FOOTBALL_27,
        confidence_threshold=0.5,
    )
    rt = OutcomeRuntime(config, bus, identity.session_head_ns)
    rt.start()
    bus.emit_raw(
        source_lobe=SourceLobe.FUSION,
        event_type=EventType.GAME_DETECTED,
        payload={"profile_id": "ncaa_football_27", "confidence": 0.9},
        session_head_ns=identity.session_head_ns,
    )
    return rt, bus, identity, jsonl_path


def _emit_ctx(bus, identity, ctx):
    bus.emit_raw(
        source_lobe=SourceLobe.VISUAL,
        event_type=EventType.VISUAL_CONTEXT,
        payload=ctx.to_dict(),
        session_head_ns=identity.session_head_ns,
    )


def _read_events(jsonl_path: Path) -> list[dict]:
    if not jsonl_path.exists():
        return []
    events = []
    for line in jsonl_path.read_text(encoding="utf-8").strip().splitlines():
        if not line:
            continue
        ev = json.loads(line)
        if ev.get("type") == "outcome_event":
            events.append(ev["payload"])
    return events


# ── Touchdown inference ──────────────────────────────────────────────────────


def test_touchdown_7_points():
    with tempfile.TemporaryDirectory() as tmp:
        rt, bus, identity, jp = _setup(Path(tmp))
        _emit_ctx(bus, identity, _make_ctx(home_score=0, away_score=0))
        _emit_ctx(bus, identity, _make_ctx(home_score=7, away_score=0))
        rt.stop()
        events = _read_events(jp)
        td = [e for e in events if e["event_name"] == "touchdown"]
        assert len(td) == 1, f"Expected 1 touchdown, got {len(td)}"
        assert td[0]["fields"]["delta"] == 7
        assert td[0]["fields"]["pat_type"] == "kick"


def test_touchdown_8_with_two_point():
    with tempfile.TemporaryDirectory() as tmp:
        rt, bus, identity, jp = _setup(Path(tmp))
        _emit_ctx(bus, identity, _make_ctx(home_score=0, away_score=0))
        _emit_ctx(bus, identity, _make_ctx(home_score=8, away_score=0))
        rt.stop()
        events = _read_events(jp)
        td = [e for e in events if e["event_name"] == "touchdown"]
        tpc = [e for e in events if e["event_name"] == "two_point_conversion"]
        assert len(td) == 1
        assert len(tpc) == 1
        assert td[0]["fields"]["pat_type"] == "two_point"


def test_field_goal_3_points():
    with tempfile.TemporaryDirectory() as tmp:
        rt, bus, identity, jp = _setup(Path(tmp))
        _emit_ctx(bus, identity, _make_ctx(away_score=0))
        _emit_ctx(bus, identity, _make_ctx(away_score=3))
        rt.stop()
        events = _read_events(jp)
        fg = [e for e in events if e["event_name"] == "field_goal"]
        assert len(fg) == 1
        assert fg[0]["fields"]["delta"] == 3


def test_safety_2_points():
    with tempfile.TemporaryDirectory() as tmp:
        rt, bus, identity, jp = _setup(Path(tmp))
        _emit_ctx(bus, identity, _make_ctx(home_score=0))
        _emit_ctx(bus, identity, _make_ctx(home_score=2))
        rt.stop()
        events = _read_events(jp)
        saf = [e for e in events if e["event_name"] == "safety"]
        assert len(saf) == 1


# ── Red zone entry ───────────────────────────────────────────────────────────


def test_red_zone_entry():
    with tempfile.TemporaryDirectory() as tmp:
        rt, bus, identity, jp = _setup(Path(tmp))
        _emit_ctx(bus, identity, _make_ctx(field_position="own 25"))
        _emit_ctx(bus, identity, _make_ctx(field_position="opp 15"))
        rt.stop()
        events = _read_events(jp)
        rz = [e for e in events if e["event_name"] == "red_zone_entry"]
        assert len(rz) == 1
        assert rz[0]["fields"]["yard_line"] == 85


def test_red_zone_no_duplicate():
    with tempfile.TemporaryDirectory() as tmp:
        rt, bus, identity, jp = _setup(Path(tmp))
        _emit_ctx(bus, identity, _make_ctx(field_position="own 25"))
        _emit_ctx(bus, identity, _make_ctx(field_position="opp 10"))
        _emit_ctx(bus, identity, _make_ctx(field_position="opp 5"))
        rt.stop()
        events = _read_events(jp)
        rz = [e for e in events if e["event_name"] == "red_zone_entry"]
        assert len(rz) == 1


# ── Two-minute warning ───────────────────────────────────────────────────────


def test_two_minute_warning_q2():
    with tempfile.TemporaryDirectory() as tmp:
        rt, bus, identity, jp = _setup(Path(tmp))
        _emit_ctx(bus, identity, _make_ctx(quarter=2, clock_seconds=180))
        _emit_ctx(bus, identity, _make_ctx(quarter=2, clock_seconds=115))
        rt.stop()
        events = _read_events(jp)
        tw = [e for e in events if e["event_name"] == "two_minute_warning"]
        assert len(tw) == 1
        assert tw[0]["fields"]["quarter"] == 2


def test_two_minute_warning_q4():
    with tempfile.TemporaryDirectory() as tmp:
        rt, bus, identity, jp = _setup(Path(tmp))
        _emit_ctx(bus, identity, _make_ctx(quarter=4, clock_seconds=130))
        _emit_ctx(bus, identity, _make_ctx(quarter=4, clock_seconds=90))
        rt.stop()
        events = _read_events(jp)
        tw = [e for e in events if e["event_name"] == "two_minute_warning"]
        assert len(tw) == 1


def test_two_minute_warning_not_q1():
    with tempfile.TemporaryDirectory() as tmp:
        rt, bus, identity, jp = _setup(Path(tmp))
        _emit_ctx(bus, identity, _make_ctx(quarter=1, clock_seconds=180))
        _emit_ctx(bus, identity, _make_ctx(quarter=1, clock_seconds=100))
        rt.stop()
        events = _read_events(jp)
        tw = [e for e in events if e["event_name"] == "two_minute_warning"]
        assert len(tw) == 0


def test_two_minute_warning_once_per_quarter():
    with tempfile.TemporaryDirectory() as tmp:
        rt, bus, identity, jp = _setup(Path(tmp))
        _emit_ctx(bus, identity, _make_ctx(quarter=2, clock_seconds=130))
        _emit_ctx(bus, identity, _make_ctx(quarter=2, clock_seconds=115))
        _emit_ctx(bus, identity, _make_ctx(quarter=2, clock_seconds=90))
        _emit_ctx(bus, identity, _make_ctx(quarter=2, clock_seconds=50))
        rt.stop()
        events = _read_events(jp)
        tw = [e for e in events if e["event_name"] == "two_minute_warning"]
        assert len(tw) == 1


# ── A2A orchestrator intervals ───────────────────────────────────────────────


def test_a2a_intervals_have_new_events():
    from qoresence.a2a.orchestrator import _INTERVAL_BY_REASON
    for reason in ("touchdown", "field_goal", "safety", "two_point_conversion",
                   "turnover", "red_zone_entry", "two_minute_warning"):
        assert reason in _INTERVAL_BY_REASON, f"{reason} missing from _INTERVAL_BY_REASON"


# ── Profile includes new events ──────────────────────────────────────────────


def test_profile_has_new_events():
    new_events = {
        "touchdown", "field_goal", "safety", "two_point_conversion",
        "two_minute_warning", "red_zone_entry",
    }
    for ev in new_events:
        assert ev in NCAA_FOOTBALL_27_PROFILE.event_types, f"{ev} not in profile event_types"
