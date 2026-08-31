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
    # True when Gemini scoreboard VLM force-locked the board (confirm path).
    score_vlm_locked: bool = False
    confirm_ticket_id: str = ""
    # Canonical seeing-path speech. Observation only; never a last-good score.
    board_why: str = ""
    title_hysteresis: str | None = None
    title_claim: bool | None = None

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
    home_team: str | None = None
    away_team: str | None = None
    home_team_name: str | None = None
    away_team_name: str | None = None
    # Madden / NFL / CFB scorebug: AWAY left, HOME right unless true.
    home_left: bool | None = None
    home_color: str | None = None
    away_color: str | None = None
    home_logo: str | None = None
    away_logo: str | None = None
    home_hex: str | None = None
    away_hex: str | None = None
    on_screen_player: str | None = None
    on_screen_player_team: str | None = None
    on_screen_player_jersey: int | None = None
    nameplate_ambiguous: bool = False
    nameplate_match: str | None = None
    roster_loaded: bool = False

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
        self._operator_pin: str | None = None

    @property
    def state(self) -> SituationState:
        return self._state

    def update(self, event: BaseEvent) -> None:
        """Ingest a Qoresence event and refresh the situation."""
        if event.type == EventType.GAME_DETECTED:
            self._handle_game_detected(event.payload)
        elif event.type == EventType.TITLE_PRESENCE:
            self._handle_title_presence(event.payload)
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

    def seed_profile(self, profile_id: str | None, *, pinned: bool = False) -> None:
        if profile_id:
            self._state.game_profile = str(profile_id)
            if pinned:
                self._operator_pin = str(profile_id)

    def _maybe_apply_profile(self, profile_id: Any) -> None:
        if not profile_id:
            return
        got = str(profile_id)
        if self._operator_pin and got != self._operator_pin:
            return
        self._state.game_profile = got

    def _handle_game_detected(self, payload: dict[str, Any]) -> None:
        self._maybe_apply_profile(payload.get("profile_id"))

    def _handle_title_presence(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        hyst = payload.get("hysteresis_state")
        if hyst:
            self._state.title_hysteresis = str(hyst)
        if "claim" in payload:
            self._state.title_claim = bool(payload.get("claim"))
        if payload.get("claim") and payload.get("profile_id"):
            self._maybe_apply_profile(payload.get("profile_id"))

    def _handle_visual_context(self, event: BaseEvent) -> None:
        try:
            ctx = VisualContext.from_dict(event.payload)
        except Exception:
            return

        self._last_visual_context_ns = event.clock_ns
        if ctx.game_state is not None:
            self._state.game_state = (
                ctx.game_state.value if hasattr(ctx.game_state, "value") else str(ctx.game_state)
            )

        # Map title → canonical profile (same logic as visual.py _merge_scoreboard)
        # Ensures published situation has cfb_27 when title is CFB, even if config was madden_27
        ctx_profile = getattr(ctx, "game_profile", None)
        ctx_title = getattr(ctx, "game_title", None)
        if ctx_profile or ctx_title:
            title_lower = str(ctx_title or "").lower()
            profile_lower = str(ctx_profile or "").lower()
            if "college" in title_lower or "ncaa" in title_lower or "cfb" in title_lower or "college football" in title_lower:
                ctx.game_profile = "cfb_27"
            elif "madden" in title_lower or "madden" in profile_lower:
                ctx.game_profile = "madden_27"
        # Fail-closed: never adopt score_vlm_locked without a ConfirmTicket id.
        tid = str(getattr(ctx, "confirm_ticket_id", "") or "")
        why = str(getattr(ctx, "board_why", "") or "").strip()
        if why:
            self._state.board_why = why
        elif isinstance(getattr(ctx, "details", None), dict):
            detail_why = str(ctx.details.get("board_why") or "").strip()
            if detail_why:
                self._state.board_why = detail_why
        if tid:
            self._state.confirm_ticket_id = tid
        if ctx.score_vlm_locked and tid:
            self._state.score_vlm_locked = True
            self._state.board_why = "confirm_ticket"
        elif ctx.score_vlm_locked and not tid:
            # Unlicensed lock claim — ignore.
            if not self._state.board_why:
                self._state.board_why = "no_ticket"
        try:
            from qoresence.profiles.cfb27_product import effective_game_state
            from qoresence.sync.play_phrase import note_game_state

            self._state.game_state = effective_game_state(
                self._state.game_state,
                locked=bool(self._state.score_vlm_locked),
                quarter=self._state.quarter
                if self._state.quarter is not None
                else getattr(ctx, "quarter", None),
                down=self._state.down
                if self._state.down is not None
                else getattr(ctx, "down", None),
            )
            note_game_state(self._state.game_state)
        except Exception:
            pass
        if ctx.game_category is not None:
            self._state.game_category = (
                ctx.game_category.value
                if hasattr(ctx.game_category, "value")
                else str(ctx.game_category)
            )
        if ctx.game_profile:
            rejected = bool(self._operator_pin and str(ctx.game_profile) != self._operator_pin)
            self._maybe_apply_profile(ctx.game_profile)
            if ctx.game_title and not rejected:
                self._state.game_title = ctx.game_title
        elif ctx.game_title:
            self._state.game_title = ctx.game_title
        self._state.visual_confidence = ctx.confidence
        if ctx.game_category and ctx.game_category.value == "football":
            # Scores: only apply if plausible (OCR often emits 17-2 for a real 17-17)
            # VLM-locked scores bypass this gate — the scoreboard referee is the
            # authority and may correct a prior bad OCR lock (e.g. 20-20 → 20-0).
            hs, aws = ctx.home_score, ctx.away_score
            if not ctx.score_vlm_locked:
                if hs is not None and not self._score_plausible(self._state.home_score, hs):
                    hs = None
                if aws is not None and not self._score_plausible(self._state.away_score, aws):
                    aws = None
            id_ok = True
            sides_ok = True
            try:
                from qoresence.profiles.cfb27_product import (
                    identity_compatible,
                    identity_sides_stable,
                )

                profile = self._state.game_profile or getattr(ctx, "game_profile", None)
                if self._state.score_vlm_locked and (
                    self._state.home_team or self._state.away_team
                ):
                    id_ok = identity_compatible(
                        self._state.home_team,
                        self._state.away_team,
                        getattr(ctx, "home_team", None),
                        getattr(ctx, "away_team", None),
                        profile=profile,
                    )
                    sides_ok = identity_sides_stable(
                        self._state.home_team,
                        self._state.away_team,
                        getattr(ctx, "home_team", None),
                        getattr(ctx, "away_team", None),
                        profile=profile,
                    )
            except Exception:
                id_ok = True
                sides_ok = True
            # Hysteresis patch: when incoming licensed lock has incompatible identity,
            # adopt it. New confirm_ticket_id overrides prior identity.
            ticket_changed = tid and tid != self._state.confirm_ticket_id
            licensed_incoming = ctx.score_vlm_locked and tid
            force_adopt = licensed_incoming and (not id_ok or ticket_changed)
            ident: dict[str, Any] = {}
            if id_ok and sides_ok:
                ident = {
                    "home_team": getattr(ctx, "home_team", None),
                    "away_team": getattr(ctx, "away_team", None),
                    "home_team_name": getattr(ctx, "home_team_name", None),
                    "away_team_name": getattr(ctx, "away_team_name", None),
                    "home_color": getattr(ctx, "home_color", None),
                    "away_color": getattr(ctx, "away_color", None),
                    "home_logo": getattr(ctx, "home_logo", None),
                    "away_logo": getattr(ctx, "away_logo", None),
                    "home_hex": getattr(ctx, "home_hex", None),
                    "away_hex": getattr(ctx, "away_hex", None),
                }
            elif force_adopt:
                # New licensed lock with incompatible identity: adopt incoming.
                ident = {
                    "home_team": getattr(ctx, "home_team", None),
                    "away_team": getattr(ctx, "away_team", None),
                    "home_team_name": getattr(ctx, "home_team_name", None),
                    "away_team_name": getattr(ctx, "away_team_name", None),
                    "home_color": getattr(ctx, "home_color", None),
                    "away_color": getattr(ctx, "away_color", None),
                    "home_logo": getattr(ctx, "home_logo", None),
                    "away_logo": getattr(ctx, "away_logo", None),
                    "home_hex": getattr(ctx, "home_hex", None),
                    "away_hex": getattr(ctx, "away_hex", None),
                }
            elif not id_ok and not ctx.score_vlm_locked:
                # Stranger ticker pair — do not take its scores either
                hs, aws = None, None
            incoming_home_left = getattr(ctx, "home_left", None)
            if incoming_home_left is not None and (
                sides_ok or not (self._state.home_team or self._state.away_team)
            ):
                ident["home_left"] = bool(incoming_home_left)
            self._apply_if_set(
                home_score=hs,
                away_score=aws,
                quarter=ctx.quarter,
                down=ctx.down,
                yards_to_go=ctx.yards_to_go,
                possession=ctx.possession,
                field_position=ctx.field_position,
                play_clock=ctx.play_clock,
                game_clock_seconds=ctx.clock_seconds,
                on_screen_player=getattr(ctx, "on_screen_player", None),
                on_screen_player_team=getattr(ctx, "on_screen_player_team", None),
                on_screen_player_jersey=getattr(ctx, "on_screen_player_jersey", None),
                nameplate_ambiguous=bool(getattr(ctx, "nameplate_ambiguous", False)),
                nameplate_match=getattr(ctx, "nameplate_match", None),
                roster_loaded=bool(getattr(ctx, "roster_loaded", False)),
                **ident,
            )

        if ctx.game_category and ctx.game_category.value == "shooter":
            self._apply_if_set(
                health=getattr(ctx, "health", None),
                ammo=getattr(ctx, "ammo", None),
                kills=getattr(ctx, "kills", None),
                deaths=getattr(ctx, "deaths", None),
                score=getattr(ctx, "score", None),
            )

    def _apply_if_set(self, **kwargs: Any) -> None:
        """Update state fields only when the incoming value is not None."""
        for key, value in kwargs.items():
            if value is not None and value != "":
                setattr(self._state, key, value)

    @staticmethod
    def _score_plausible(prev: Any, new: Any) -> bool:
        """Reject large score drops / nonsense (OCR flicker). Stabilizer is primary."""
        if new is None:
            return False
        try:
            n = int(new)
        except Exception:
            return False
        if not (0 <= n <= 99):
            return False
        if prev is None:
            return True
        try:
            p = int(prev)
        except Exception:
            return True
        d = n - p
        if d <= -7:
            return False
        if d < 0:
            return False
        if d > 14:
            return False
        return True

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
            "score_vlm_locked": bool(s.score_vlm_locked),
            "scoreboard_locked": bool(s.score_vlm_locked),
            "confirm_ticket_id": s.confirm_ticket_id or "",
            "has_confirm_ticket": bool(s.confirm_ticket_id),
            "board_why": s.board_why or "",
            "title_hysteresis": s.title_hysteresis,
            "title_claim": s.title_claim,
            "home_score": s.home_score,
            "away_score": s.away_score,
            "quarter": s.quarter,
            "down": s.down,
            "yards_to_go": s.yards_to_go,
            "possession": s.possession,
            "field_position": s.field_position,
            "play_clock": s.play_clock,
            "game_clock_seconds": s.game_clock_seconds,
            "home_team": s.home_team,
            "away_team": s.away_team,
            "home_left": s.home_left,
            "home_team_name": s.home_team_name,
            "away_team_name": s.away_team_name,
            "home_color": s.home_color,
            "away_color": s.away_color,
            "home_logo": s.home_logo,
            "away_logo": s.away_logo,
            "home_hex": s.home_hex,
            "away_hex": s.away_hex,
            "on_screen_player": s.on_screen_player,
            "on_screen_player_team": s.on_screen_player_team,
            "on_screen_player_jersey": s.on_screen_player_jersey,
            "nameplate_ambiguous": bool(s.nameplate_ambiguous),
            "nameplate_match": s.nameplate_match,
            "roster_loaded": bool(s.roster_loaded),
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
