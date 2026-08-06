"""
Rolling situation model for ClutchBot.

Maintains a lightweight, observable snapshot of the current game state by
listening to Qoresence bus events. This snapshot is the input to the
MomentScorer.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from qoresence.core import BaseEvent, EventType
from qoresence.vision.visual_context import VisualContext


@dataclass
class ControllerSnapshot:
    """Rolling controller-derived signals."""
    last_input_ns: int = 0
    apm_5s: float = 0.0
    stick_motion_5s: float = 0.0
    trigger_events_5s: int = 0


@dataclass
class SituationState:
    """Current situation that ClutchBot acts on."""
    game_profile: str | None = None
    game_state: str | None = None
    game_category: str | None = None
    game_title: str | None = None
    visual_confidence: float = 0.0

    # Football
    home_score: int | None = None
    away_score: int | None = None
    quarter: int | None = None
    down: int | None = None
    yards_to_go: int | None = None
    possession: str | None = None
    field_position: str | None = None
    play_clock: int | None = None
    game_clock_seconds: int | None = None

    # Shooter
    health: int | None = None
    ammo: int | None = None
    kills: int | None = None
    deaths: int | None = None
    score: int | None = None

    # Controller / presence
    controller: ControllerSnapshot = field(default_factory=ControllerSnapshot)
    presence_sync_ok: bool | None = None
    last_outcome_event: str | None = None
    last_outcome_fields: dict[str, Any] = field(default_factory=dict)


class SituationModel:
    """Maintains the rolling SituationState from bus events."""

    def __init__(self, window_s: float = 5.0):
        self.window_s = window_s
        self._state = SituationState()
        self._controller_events: deque[tuple[int, str, dict[str, Any]]] = deque()
        self._last_visual_context_ns: int = 0

    @property
    def state(self) -> SituationState:
        return self._state

    def update(self, event: BaseEvent) -> None:
        """Ingest a Qoresence event and refresh the situation."""
        if event.type == EventType.GAME_DETECTED:
            self._handle_game_detected(event.payload)
        elif event.type == EventType.VISUAL_CONTEXT:
            self._handle_visual_context(event)
        elif event.type == EventType.OUTCOME_EVENT:
            self._handle_outcome_event(event.payload)
        elif event.type == EventType.CONTROLLER_EVENT:
            self._handle_controller_event(event)
        elif event.type == EventType.TRIGGER_ONSET:
            self._handle_trigger_onset(event)
        elif event.type == EventType.STICK_MOTION:
            self._handle_stick_motion(event)
        elif event.type == EventType.PRESENCE_REPORT:
            self._handle_presence_report(event.payload)

    def _handle_game_detected(self, payload: dict[str, Any]) -> None:
        self._state.game_profile = payload.get("profile_id")

    def _handle_visual_context(self, event: BaseEvent) -> None:
        try:
            ctx = VisualContext.from_dict(event.payload)
        except Exception:
            return

        self._last_visual_context_ns = event.clock_ns
        if ctx.game_state is not None:
            self._state.game_state = ctx.game_state.value if hasattr(ctx.game_state, "value") else str(ctx.game_state)
        if ctx.game_category is not None:
            self._state.game_category = ctx.game_category.value if hasattr(ctx.game_category, "value") else str(ctx.game_category)
        if ctx.game_title:
            self._state.game_title = ctx.game_title
        self._state.visual_confidence = ctx.confidence

        if ctx.game_category and ctx.game_category.value == "football":
            self._apply_if_set(
                home_score=ctx.home_score,
                away_score=ctx.away_score,
                quarter=ctx.quarter,
                down=ctx.down,
                yards_to_go=ctx.yards_to_go,
                possession=ctx.possession,
                field_position=ctx.field_position,
                play_clock=ctx.play_clock,
                game_clock_seconds=ctx.clock_seconds,
            )

        if ctx.game_category and ctx.game_category.value == "shooter":
            self._apply_if_set(
                health=ctx.health,
                ammo=ctx.ammo,
                kills=ctx.kills,
                deaths=ctx.deaths,
                score=ctx.score,
            )

    def _apply_if_set(self, **kwargs: Any) -> None:
        """Update state fields only when the incoming value is not None."""
        for key, value in kwargs.items():
            if value is not None and value != "":
                setattr(self._state, key, value)

    def _handle_outcome_event(self, payload: dict[str, Any]) -> None:
        self._state.last_outcome_event = payload.get("event_name")
        self._state.last_outcome_fields = payload.get("fields") or {}

    def _handle_controller_event(self, event: BaseEvent) -> None:
        self._controller_events.append((event.clock_ns, "button", event.payload))
        self._recompute_controller_stats(event.clock_ns)

    def _handle_trigger_onset(self, event: BaseEvent) -> None:
        self._controller_events.append((event.clock_ns, "trigger", event.payload))
        self._recompute_controller_stats(event.clock_ns)

    def _handle_stick_motion(self, event: BaseEvent) -> None:
        self._controller_events.append((event.clock_ns, "stick", event.payload))
        self._recompute_controller_stats(event.clock_ns)

    def _recompute_controller_stats(self, now_ns: int) -> None:
        window_ns = int(self.window_s * 1_000_000_000)
        cutoff = now_ns - window_ns

        while self._controller_events and self._controller_events[0][0] < cutoff:
            self._controller_events.popleft()

        count = len(self._controller_events)
        # APM-ish: count per 60s window, scaled from 5s
        self._state.controller.apm_5s = (count / self.window_s) * 60.0 if self.window_s > 0 else 0.0

        triggers = sum(1 for _, kind, _ in self._controller_events if kind == "trigger")
        self._state.controller.trigger_events_5s = triggers

        # Stick motion magnitude
        stick_magnitude = 0.0
        for _ts, kind, payload in self._controller_events:
            if kind == "stick":
                x = payload.get("x", 0.0) or 0.0
                y = payload.get("y", 0.0) or 0.0
                stick_magnitude += (x * x + y * y) ** 0.5
        self._state.controller.stick_motion_5s = stick_magnitude

        if self._controller_events:
            self._state.controller.last_input_ns = self._controller_events[-1][0]

    def _handle_presence_report(self, payload: dict[str, Any]) -> None:
        self._state.presence_sync_ok = payload.get("presence_sync_ok")

    def to_dict(self) -> dict[str, Any]:
        """Serialize for the viewer panel and debug."""
        s = self._state
        return {
            "game_profile": s.game_profile,
            "game_state": s.game_state,
            "game_category": s.game_category,
            "game_title": s.game_title,
            "visual_confidence": s.visual_confidence,
            "home_score": s.home_score,
            "away_score": s.away_score,
            "quarter": s.quarter,
            "down": s.down,
            "yards_to_go": s.yards_to_go,
            "possession": s.possession,
            "field_position": s.field_position,
            "play_clock": s.play_clock,
            "game_clock_seconds": s.game_clock_seconds,
            "health": s.health,
            "ammo": s.ammo,
            "kills": s.kills,
            "deaths": s.deaths,
            "score": s.score,
            "controller_apm": s.controller.apm_5s,
            "controller_triggers_5s": s.controller.trigger_events_5s,
            "controller_stick_motion_5s": s.controller.stick_motion_5s,
            "presence_sync_ok": s.presence_sync_ok,
            "last_outcome_event": s.last_outcome_event,
        }
