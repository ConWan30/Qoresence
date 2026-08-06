"""
MomentScorer for ClutchBot.

Decides whether the current situation is worth a chat message, clip, or other
action. Phase 1 is rule- and template-driven. The design is intentionally
modular so a small LLM or learned scorer can be swapped in later.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from .situation_model import SituationState

log = logging.getLogger(__name__)


@dataclass
class ScoredMoment:
    """A scored moment with an action plan."""
    triggered: bool
    weight: float
    action: str  # "chat", "clip", "prediction", "none"
    message: str
    reason: str
    cooldown_key: str


class MomentScorer:
    """Score game situations and generate actions."""

    def __init__(self, persona: str = "neutral"):
        self.persona = persona
        self._last_trigger: dict[str, float] = {}

    def score(
        self,
        state: SituationState,
        event_type: str | None = None,
        event_payload: dict[str, Any] | None = None,
    ) -> ScoredMoment:
        """Score the current situation and return a moment plan."""
        # game_detected is allowed before the first visual_context arrives.
        if event_type == "game_detected":
            return self._score_game_detected(state)

        if state.game_state != "gameplay":
            return ScoredMoment(False, 0.0, "none", "", "not gameplay", "")

        # High-signal outcome events first
        if event_type == "outcome_event" and event_payload:
            return self._score_outcome(state, event_payload)

        if event_type == "visual_context":
            return self._score_visual_context(state, event_payload or {})

        return ScoredMoment(False, 0.0, "none", "", "no trigger", "")

    def _score_outcome(self, state: SituationState, payload: dict[str, Any]) -> ScoredMoment:
        event_name = payload.get("event_name", "")
        fields = payload.get("fields", {}) or {}

        if event_name == "score_changed":
            return self._score_score_changed(state, fields)

        if event_name == "turnover":
            return self._score_turnover(state, fields)

        if event_name == "first_down" and self._is_red_zone(state):
            return self._build_moment(
                weight=0.6,
                action="chat",
                message=self._first_down_message(state),
                reason="first down in red zone",
                cooldown_key="first_down",
            )

        if event_name == "possession_changed":
            return self._score_possession_change(state, fields)

        return ScoredMoment(False, 0.0, "none", "", f"outcome {event_name} not chat-worthy", "")

    def _score_score_changed(self, state: SituationState, fields: dict[str, Any]) -> ScoredMoment:
        home = fields.get("home_score", state.home_score)
        away = fields.get("away_score", state.away_score)

        margin = abs((home or 0) - (away or 0))
        quarter = state.quarter or 0
        weight = 0.6

        if quarter >= 4:
            weight += 0.3
        if margin <= 8:
            weight += 0.1
        if self._is_red_zone(state):
            weight += 0.1

        if state.controller.apm_5s > 80:
            weight += 0.1

        message = self._score_message(state, home, away)
        return self._build_moment(
            weight=min(weight, 1.0),
            action="chat",
            message=message,
            reason="score changed",
            cooldown_key="score",
        )

    def _score_turnover(self, state: SituationState, fields: dict[str, Any]) -> ScoredMoment:
        weight = 0.7
        if (state.quarter or 0) >= 4:
            weight += 0.2

        return self._build_moment(
            weight=min(weight, 1.0),
            action="chat",
            message=self._turnover_message(state, fields),
            reason="turnover",
            cooldown_key="turnover",
        )

    def _score_possession_change(self, state: SituationState, fields: dict[str, Any]) -> ScoredMoment:
        if not self._is_red_zone(state):
            return ScoredMoment(False, 0.0, "none", "", "possession changed outside red zone", "")

        weight = 0.6
        if (state.quarter or 0) >= 4:
            weight += 0.2

        return self._build_moment(
            weight=min(weight, 1.0),
            action="chat",
            message=self._possession_message(state, fields),
            reason="red-zone possession change",
            cooldown_key="possession",
        )

    def _score_game_detected(self, state: SituationState) -> ScoredMoment:
        return self._build_moment(
            weight=0.4,
            action="chat",
            message=f"Qoresence is locked on: {state.game_title or state.game_profile or 'game detected'}.",
            reason="game detected",
            cooldown_key="game_detected",
        )

    def _score_visual_context(self, state: SituationState, payload: dict[str, Any]) -> ScoredMoment:
        # Only react to visual context if it is a late/close drive worth narrating.
        quarter = state.quarter or 0
        margin = abs((state.home_score or 0) - (state.away_score or 0))
        if quarter >= 4 and margin <= 8 and self._is_red_zone(state) and state.down == 1:
            return self._build_moment(
                weight=0.6,
                action="chat",
                message=f"Late drive in the red zone — {state.home_score or '?'}-{state.away_score or '?'} Q{quarter}.",
                reason="late red-zone drive",
                cooldown_key="late_drive",
            )
        return ScoredMoment(False, 0.0, "none", "", "visual context not chat-worthy", "")

    # ──────────────────────────────────────────────────────────────────────────
    # MESSAGE TEMPLATES
    # ──────────────────────────────────────────────────────────────────────────

    def _score_message(self, state: SituationState, home: Any, away: Any) -> str:
        quarter = state.quarter
        down = state.down
        ytg = state.yards_to_go

        prefix = "Score update"
        if quarter:
            prefix += f" — Q{quarter}"

        score_str = f"{home or '?'} - {away or '?'}"
        if state.possession:
            score_str += f" | possession: {state.possession}"

        if down is not None and ytg is not None:
            score_str += f" | {down} & {ytg}"

        if state.controller.apm_5s > 80:
            score_str += f" | APM {int(state.controller.apm_5s)}"

        return f"{prefix}: {score_str}"

    def _turnover_message(self, state: SituationState, fields: dict[str, Any]) -> str:
        msg = "Turnover!"
        if state.quarter:
            msg += f" Q{state.quarter}"
        if state.possession:
            msg += f" — {state.possession} ball"
        if state.home_score is not None and state.away_score is not None:
            msg += f" | {state.home_score}-{state.away_score}"
        return msg

    def _first_down_message(self, state: SituationState) -> str:
        msg = "First down in the red zone"
        if state.possession:
            msg += f" — {state.possession}"
        if state.down is not None and state.yards_to_go is not None:
            msg += f" | {state.down} & {state.yards_to_go}"
        return msg

    def _possession_message(self, state: SituationState, fields: dict[str, Any]) -> str:
        prev = fields.get("prev_possession")
        cur = fields.get("possession") or state.possession
        if prev and cur:
            return f"Red zone possession switch: {prev} → {cur}"
        return f"Red zone possession change: {cur or 'unknown'}"

    # ──────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────────────────────

    def _is_red_zone(self, state: SituationState) -> bool:
        # Look at field_position string, e.g. "opp 10" or "opponent 15".
        # If unavailable, fall back to a conservative false.
        pos = (state.field_position or "").lower()
        if not pos:
            return False

        # Parse a trailing number after "opp" / "opponent"
        match = re.search(r"opp(?:onent)?\s*(\d+)", pos)
        if match:
            yard = int(match.group(1))
            return yard <= 20

        # Common shorthand: "own" is never red zone.
        if "own" in pos:
            return False

        return False

    def _build_moment(
        self,
        weight: float,
        action: str,
        message: str,
        reason: str,
        cooldown_key: str,
    ) -> ScoredMoment:
        now = time.time()
        last = self._last_trigger.get(cooldown_key, 0.0)
        # Hard cooldown per category (30s minimum for chat)
        if action == "chat" and now - last < 30.0:
            return ScoredMoment(False, weight, "none", "", f"cooldown for {cooldown_key}", cooldown_key)

        self._last_trigger[cooldown_key] = now
        return ScoredMoment(True, weight, action, message, reason, cooldown_key)
