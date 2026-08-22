"""Outcome lobe heartbeat prevents temporal_desync on stable game state."""

from __future__ import annotations

from qoresence.core import EventType, SourceLobe
from qoresence.core.types import BaseEvent
from qoresence.core.unified_config import OutcomeConfig
from qoresence.lobes.outcome import OutcomeRuntime
from qoresence.vision.visual_context import GameCategory, GameState, VisualContext


class _FakeBus:
    def __init__(self):
        self.events: list[BaseEvent] = []
        self._subs: list = []

    def emit_raw(self, **kw):
        ev = BaseEvent(
            session_id=kw.get("session_id", "s"),
            clock_ns=kw.get("clock_ns_override", 1),
            source_lobe=kw["source_lobe"],
            type=kw["event_type"],
            payload=kw["payload"],
        )
        self.events.append(ev)

    def subscribe(self, cb):
        self._subs.append(cb)
        return lambda: None


def _football_ctx(**kw):
    defaults = {
        "game_category": GameCategory.FOOTBALL,
        "game_state": GameState.GAMEPLAY,
        "confidence": 0.9,
        "home_score": 17,
        "away_score": 17,
        "quarter": 2,
    }
    defaults.update(kw)
    return VisualContext(**defaults)


def test_heartbeat_emitted_on_stable_state():
    """No score change → outcome still emits a heartbeat, not silence."""
    bus = _FakeBus()
    cfg = OutcomeConfig(enabled=True, game_profile="ncaa_football_27")
    rt = OutcomeRuntime(cfg, bus, session_head_ns=1)
    rt.start()

    # First visual context — syncs state, no heartbeat yet (prev_context is None)
    ctx1 = _football_ctx()
    rt._on_event(
        BaseEvent(
            session_id="s",
            clock_ns=1,
            source_lobe=SourceLobe.VISUAL,
            type=EventType.VISUAL_CONTEXT,
            payload=ctx1.to_dict(),
        )
    )

    # Second visual context — same scores, no state change
    bus.events.clear()
    rt._on_event(
        BaseEvent(
            session_id="s",
            clock_ns=2,
            source_lobe=SourceLobe.VISUAL,
            type=EventType.VISUAL_CONTEXT,
            payload=ctx1.to_dict(),
        )
    )

    heartbeats = [e for e in bus.events if e.type == EventType.HEARTBEAT]
    assert len(heartbeats) == 1
    assert heartbeats[0].source_lobe == SourceLobe.OUTCOME
    assert heartbeats[0].payload["home_score"] == 17


def test_heartbeat_not_emitted_on_menu():
    """Menu screens should not produce heartbeats."""
    bus = _FakeBus()
    cfg = OutcomeConfig(enabled=True, game_profile="ncaa_football_27")
    rt = OutcomeRuntime(cfg, bus, session_head_ns=1)
    rt.start()

    ctx = _football_ctx(game_state=GameState.MENU)
    bus.events.clear()
    rt._on_event(
        BaseEvent(
            session_id="s",
            clock_ns=1,
            source_lobe=SourceLobe.VISUAL,
            type=EventType.VISUAL_CONTEXT,
            payload=ctx.to_dict(),
        )
    )
    assert not any(e.type == EventType.HEARTBEAT for e in bus.events)


def test_score_change_still_emits_outcome_event_and_heartbeat():
    """Score change emits both an OUTCOME_EVENT and a HEARTBEAT."""
    bus = _FakeBus()
    cfg = OutcomeConfig(enabled=True, game_profile="ncaa_football_27")
    rt = OutcomeRuntime(cfg, bus, session_head_ns=1)
    rt.start()

    ctx1 = _football_ctx(home_score=17, away_score=17)
    rt._on_event(
        BaseEvent(
            session_id="s",
            clock_ns=1,
            source_lobe=SourceLobe.VISUAL,
            type=EventType.VISUAL_CONTEXT,
            payload=ctx1.to_dict(),
        )
    )

    bus.events.clear()
    ctx2 = _football_ctx(home_score=24, away_score=17)
    rt._on_event(
        BaseEvent(
            session_id="s",
            clock_ns=2,
            source_lobe=SourceLobe.VISUAL,
            type=EventType.VISUAL_CONTEXT,
            payload=ctx2.to_dict(),
        )
    )

    outcomes = [e for e in bus.events if e.type == EventType.OUTCOME_EVENT]
    heartbeats = [e for e in bus.events if e.type == EventType.HEARTBEAT]
    assert len(outcomes) >= 1
    assert len(heartbeats) == 1
