"""Tests for Phase 7.2: Router must-fire predicates (Trio Principle 2)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from qoresence.a2a.orchestrator import A2AOrchestrator, reset_a2a_orchestrator
from qoresence.a2a.router import (
    build_router_decision,
    evaluate_must_fire,
    get_predicates_for_category,
)
from qoresence.core import RetinaEventBus

# ── Predicate evaluation ─────────────────────────────────────────────────────


def test_big_play_predicate_fires_on_touchdown():
    """Must-fire should trigger when last_outcome_event is touchdown."""
    sit = {"game_category": "football", "last_outcome_event": "touchdown"}
    fired, pred = evaluate_must_fire(sit)
    assert fired is True
    assert pred == "big_play"


def test_big_play_predicate_fires_on_field_goal():
    sit = {"game_category": "football", "last_outcome_event": "field_goal"}
    fired, pred = evaluate_must_fire(sit)
    assert fired is True
    assert pred == "big_play"


def test_big_play_predicate_fires_on_turnover():
    sit = {"game_category": "football", "last_outcome_event": "turnover"}
    fired, pred = evaluate_must_fire(sit)
    assert fired is True
    assert pred == "big_play"


def test_two_minute_warning_predicate():
    sit = {"game_category": "football", "last_outcome_event": "two_minute_warning"}
    fired, pred = evaluate_must_fire(sit)
    assert fired is True
    assert pred == "two_minute_warning"


def test_red_zone_predicate():
    sit = {"game_category": "football", "last_outcome_event": "red_zone_entry"}
    fired, pred = evaluate_must_fire(sit)
    assert fired is True
    assert pred == "red_zone_entry"


def test_no_fire_on_benign_event():
    """Must-fire should NOT trigger on non-big-play events."""
    sit = {"game_category": "football", "last_outcome_event": "first_down"}
    fired, pred = evaluate_must_fire(sit)
    assert fired is False
    assert pred is None


def test_no_fire_on_empty_situation():
    fired, pred = evaluate_must_fire({})
    assert fired is False
    assert pred is None


def test_operator_query_predicate():
    """Force flag should trigger operator_query predicate."""
    sit = {"game_category": "football", "_force": True}
    fired, pred = evaluate_must_fire(sit)
    assert fired is True
    assert pred == "operator_query"


def test_shooter_kill_streak_predicate():
    """Shooter with high trigger activity should fire."""
    sit = {"game_category": "shooter", "controller_triggers_5s": 12}
    fired, pred = evaluate_must_fire(sit)
    assert fired is True
    assert pred == "shooter_kill_streak"


def test_shooter_no_fire_on_low_activity():
    sit = {"game_category": "shooter", "controller_triggers_5s": 2}
    fired, pred = evaluate_must_fire(sit)
    assert fired is False


def test_football_predicates_dont_fire_for_shooter():
    """Football-specific predicates should not fire for shooter games."""
    sit = {"game_category": "shooter", "last_outcome_event": "touchdown"}
    # touchdown is a football event, not a shooter event
    preds = get_predicates_for_category("shooter")
    fired, pred = evaluate_must_fire(sit, predicates=preds)
    assert fired is False  # shooter predicates don't check for touchdown


# ── Predicate registry ───────────────────────────────────────────────────────


def test_football_predicates_registered():
    preds = get_predicates_for_category("football")
    names = [p.name for p in preds]
    assert "big_play" in names
    assert "two_minute_warning" in names
    assert "red_zone_entry" in names


def test_shooter_predicates_registered():
    preds = get_predicates_for_category("shooter")
    names = [p.name for p in preds]
    assert "shooter_kill_streak" in names


def test_unknown_category_gets_all_predicates():
    preds = get_predicates_for_category("other")
    assert len(preds) >= 3  # safe default has all predicates


# ── RouterDecision log ───────────────────────────────────────────────────────


def test_router_decision_to_dict():
    d = build_router_decision(
        fired=True,
        reason="touchdown",
        situation={"game_category": "football", "last_outcome_event": "touchdown"},
        must_fire_hit="big_play",
        interval_s=6.0,
        last_trigger_age_s=30.0,
    )
    assert d.fired is True
    assert d.reason == "touchdown"
    assert d.must_fire_hit == "big_play"
    assert d.interval_s == 6.0
    dd = d.to_dict()
    assert dd["fired"] is True
    assert dd["inputs"]["game_category"] == "football"


def test_router_decision_suppressed():
    d = build_router_decision(
        fired=False,
        reason="scene_tick",
        situation={"game_category": "football"},
        must_fire_hit=None,
        interval_s=45.0,
        last_trigger_age_s=10.0,
    )
    assert d.fired is False
    assert d.must_fire_hit is None


# ── Orchestrator integration ─────────────────────────────────────────────────


def test_router_decision_emitted_on_fire():
    """A ROUTER_DECISION event should be emitted when the router fires."""
    with tempfile.TemporaryDirectory() as td:
        jsonl_path = Path(td) / "events.jsonl"
        retina_bus = RetinaEventBus(
            session_id="router_test", jsonl_path=jsonl_path, enable_ws=False
        )

        orch = A2AOrchestrator(enabled=True, min_interval_s=0.0)
        orch.bus.set_retina_mirror(retina_bus, session_id="router_test")

        situation = {
            "game_state": "gameplay",
            "game_category": "football",
            "last_outcome_event": "touchdown",
            "visual_confidence": 0.9,
        }

        # Force trigger to test router decision emission
        orch.maybe_trigger_from_drive(
            situation=situation,
            reason="touchdown",
            force=True,
        )

        # Wait briefly for async cycle
        import time as _t

        _t.sleep(0.5)

        lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line) for line in lines if line.strip()]
        router_events = [e for e in events if e["type"] == "router_decision"]

        assert len(router_events) >= 1, "No router_decision event emitted"
        assert router_events[0]["payload"]["fired"] is True
        assert router_events[0]["payload"]["reason"] == "touchdown"

        reset_a2a_orchestrator()
        retina_bus.close()


def test_must_fire_bypasses_interval():
    """A must-fire predicate should bypass the interval check."""
    with tempfile.TemporaryDirectory() as td:
        jsonl_path = Path(td) / "events.jsonl"
        retina_bus = RetinaEventBus(
            session_id="bypass_test", jsonl_path=jsonl_path, enable_ws=False
        )

        # Set a very high min_interval to test bypass
        orch = A2AOrchestrator(enabled=True, min_interval_s=999.0)
        orch.bus.set_retina_mirror(retina_bus, session_id="bypass_test")

        situation = {
            "game_state": "gameplay",
            "game_category": "football",
            "last_outcome_event": "touchdown",
            "visual_confidence": 0.9,
        }

        # First trigger — should fire because must_fire bypasses interval
        orch.maybe_trigger_from_drive(
            situation=situation,
            reason="touchdown",
        )

        import time as _t

        _t.sleep(0.5)

        lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line) for line in lines if line.strip()]
        router_events = [e for e in events if e["type"] == "router_decision"]
        fired_events = [e for e in router_events if e["payload"]["fired"]]

        assert len(fired_events) >= 1, "Must-fire did not bypass interval"
        assert fired_events[0]["payload"]["must_fire_hit"] == "big_play"

        reset_a2a_orchestrator()
        retina_bus.close()
