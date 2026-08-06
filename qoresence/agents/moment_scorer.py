"""
MomentScorer for ClutchBot.

Decides whether the current situation is worth a chat message, clip,
prediction, or other action. Phase 1 is rule- and template-driven. The design
is intentionally modular so a small LLM or learned scorer can be swapped in
later.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .helix_client import PredictionResult
from .situation_model import SituationState

log = logging.getLogger(__name__)

DEFAULT_FEATURES = frozenset({"chat"})


@dataclass
class ScoredMoment:
    """A scored moment with an action plan."""
    triggered: bool
    weight: float
    action: str  # "chat", "clip", "start_prediction", "resolve_prediction", "none"
    message: str
    reason: str
    cooldown_key: str
    payload: dict[str, Any] = field(default_factory=dict)


class MomentScorer:
    """Score game situations and generate actions."""

    # Built-in message templates keyed by situation. Format placeholders:
    # {home_score}, {away_score}, {quarter}, {down}, {yards_to_go},
    # {possession}, {field_position}, {game_title}.
    DEFAULT_TEMPLATES: dict[str, dict[str, str]] = {
        "neutral": {
            "score_changed": "Score update: {home_score}-{away_score}.",
            "turnover": "Turnover!",
            "first_down": "First down in the red zone — {possession}.",
            "possession_changed": "Possession changes to {possession}.",
            "red_zone_drive": "Red zone drive — {home_score}-{away_score} Q{quarter}.",
            "game_detected": "Qoresence is locked on: {game_title}.",
            "start_prediction": "Will they score on this drive?",
            "resolve_prediction_yes": "Drive result: score!",
            "resolve_prediction_no": "Drive result: no score.",
            "kill": "Kill confirmed — {score}!",
            "death": "Down!",
            "multi_kill": "Multi-kill! {score}!",
            "clip": "Clutch clip incoming!",
        },
        "hype": {
            "score_changed": "SCORE! {home_score}-{away_score}!",
            "turnover": "TURNOVER! Momentum shift!",
            "first_down": "FIRST DOWN! {possession} keeps it moving!",
            "possession_changed": "Ball changes hands! {possession} takes over!",
            "clip": "THAT WAS CLUTCH! 🎬",
            "red_zone_drive": "RED ZONE ALERT! {home_score}-{away_score} Q{quarter}!",
            "game_detected": "We are LIVE on {game_title}!",
            "start_prediction": "Are they punching it in?!",
            "resolve_prediction_yes": "CALLED IT! TOUCHDOWN/SCORE!",
            "resolve_prediction_no": "Drive stalls! No dice.",
            "kill": "ELIMINATED! {score}!",
            "death": "DOWNED!",
            "multi_kill": "MULTI-KILL! {score}!",
            "clip": "THAT WAS CLUTCH! 🎬",
        },
    }

    def __init__(self, persona: str = "neutral"):
        self.persona = persona
        self._templates = self._load_templates(persona)
        self._last_trigger: dict[tuple[str, str], float] = {}

    def _load_templates(self, persona: str) -> dict[str, str]:
        """Load persona templates from built-ins or a JSON file path."""
        if persona in self.DEFAULT_TEMPLATES:
            return self.DEFAULT_TEMPLATES[persona]

        path = Path(persona)
        if path.is_file():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception as e:
                log.warning(f"Failed to load persona from {persona}: {e}")

        log.warning(f"Unknown persona '{persona}'; using neutral")
        return self.DEFAULT_TEMPLATES["neutral"]

    def _message(self, key: str, state: SituationState, **extra: Any) -> str:
        """Format a persona-aware message."""
        template = self._templates.get(key, self.DEFAULT_TEMPLATES["neutral"].get(key, ""))
        if not template:
            return ""

        fmt = {
            "home_score": state.home_score if state.home_score is not None else "?",
            "away_score": state.away_score if state.away_score is not None else "?",
            "quarter": state.quarter or "?",
            "down": state.down or "?",
            "yards_to_go": state.yards_to_go or "?",
            "possession": state.possession or "",
            "field_position": state.field_position or "",
            "game_title": state.game_title or state.game_profile or "the game",
        }
        fmt.update({k: v if v is not None else "" for k, v in extra.items()})

        try:
            return template.format(**fmt)
        except (KeyError, ValueError):
            return template

    def score(
        self,
        state: SituationState,
        event_type: str | None = None,
        event_payload: dict[str, Any] | None = None,
        active_prediction: PredictionResult | None = None,
        features: set[str] | None = None,
    ) -> list[ScoredMoment]:
        """Score the current situation and return one or more moment plans."""
        features = features or DEFAULT_FEATURES

        # game_detected is allowed before the first visual_context arrives.
        if event_type == "game_detected":
            chat = self._score_game_detected(state)
            return [chat] if chat.triggered else []

        if state.game_state != "gameplay":
            return []

        # High-signal outcome events first
        if event_type == "outcome_event" and event_payload:
            return self._score_outcome(state, event_payload, active_prediction, features)

        if event_type == "visual_context":
            return self._score_visual_context(state, event_payload or {}, active_prediction, features)

        return []

    # ──────────────────────────────────────────────────────────────────────────
    # SCORERS
    # ──────────────────────────────────────────────────────────────────────────

    def _score_outcome(
        self,
        state: SituationState,
        payload: dict[str, Any],
        active_prediction: PredictionResult | None,
        features: set[str],
    ) -> list[ScoredMoment]:
        event_name = payload.get("event_name", "")
        fields = payload.get("fields", {}) or {}

        if event_name == "score_changed":
            return self._score_score_changed(state, fields, active_prediction, features)

        if event_name == "turnover":
            return self._score_turnover(state, fields, active_prediction, features)

        if event_name == "first_down" and self._is_red_zone(state):
            chat = self._build_moment(
                weight=0.6,
                action="chat",
                message=self._first_down_message(state),
                reason="first down in red zone",
                cooldown_key="first_down",
            )
            moments = [chat] if chat.triggered else []
            if "clip" in features and chat.triggered:
                clip = self._build_moment(
                    weight=0.8,
                    action="clip",
                    message=chat.message,
                    reason="red-zone first down — clip",
                    cooldown_key="clip",
                )
                if clip.triggered:
                    moments.append(clip)
            return moments

        if event_name == "possession_changed":
            return self._score_possession_change(state, fields, active_prediction, features)

        if event_name == "kill":
            return self._score_kill(state, fields, features)

        if event_name == "death":
            return self._score_death(state, fields, features)

        return []

    def _score_score_changed(
        self,
        state: SituationState,
        fields: dict[str, Any],
        active_prediction: PredictionResult | None,
        features: set[str],
    ) -> list[ScoredMoment]:
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
        chat = self._build_moment(
            weight=min(weight, 1.0),
            action="chat",
            message=message,
            reason="score changed",
            cooldown_key="score",
        )
        moments: list[ScoredMoment] = [chat] if chat.triggered else []

        if chat.triggered:
            if "clip" in features and weight >= 0.8:
                clip = self._build_moment(
                    weight=weight,
                    action="clip",
                    message=message,
                    reason="clutch score — clip",
                    cooldown_key="clip",
                )
                if clip.triggered:
                    moments.append(clip)

            if "prediction" in features and active_prediction:
                scoring_team = self._scoring_team(fields, state)
                if scoring_team is not None:
                    winning_index = 0 if scoring_team == active_prediction.offense else 1
                    resolve = self._build_moment(
                        weight=0.9,
                        action="resolve_prediction",
                        message=self._message(
                            "resolve_prediction_yes" if winning_index == 0 else "resolve_prediction_no",
                            state,
                        ),
                        reason="score_changed resolves prediction",
                        cooldown_key="prediction_resolve",
                        payload={"winning_outcome_index": winning_index},
                    )
                    if resolve.triggered:
                        moments.append(resolve)

        return moments

    def _score_turnover(
        self,
        state: SituationState,
        fields: dict[str, Any],
        active_prediction: PredictionResult | None,
        features: set[str],
    ) -> list[ScoredMoment]:
        weight = 0.7
        if (state.quarter or 0) >= 4:
            weight += 0.2

        message = self._turnover_message(state, fields)
        chat = self._build_moment(
            weight=min(weight, 1.0),
            action="chat",
            message=message,
            reason="turnover",
            cooldown_key="turnover",
        )
        moments: list[ScoredMoment] = [chat] if chat.triggered else []

        if chat.triggered and "clip" in features:
            clip = self._build_moment(
                weight=weight,
                action="clip",
                message=message,
                reason="turnover — clip",
                cooldown_key="clip",
            )
            if clip.triggered:
                moments.append(clip)

        if chat.triggered and "prediction" in features and active_prediction:
            losing_team = fields.get("prev_possession") or state.possession
            if losing_team == active_prediction.offense:
                resolve = self._build_moment(
                    weight=0.9,
                    action="resolve_prediction",
                    message=self._message("resolve_prediction_no", state),
                    reason="turnover resolves prediction as loss",
                    cooldown_key="prediction_resolve",
                    payload={"winning_outcome_index": 1},
                )
                if resolve.triggered:
                    moments.append(resolve)

        return moments

    def _score_possession_change(
        self,
        state: SituationState,
        fields: dict[str, Any],
        active_prediction: PredictionResult | None,
        features: set[str],
    ) -> list[ScoredMoment]:
        if not self._is_red_zone(state):
            return []

        weight = 0.6
        if (state.quarter or 0) >= 4:
            weight += 0.2

        message = self._possession_message(state, fields)
        chat = self._build_moment(
            weight=min(weight, 1.0),
            action="chat",
            message=message,
            reason="red-zone possession change",
            cooldown_key="possession",
        )
        moments: list[ScoredMoment] = [chat] if chat.triggered else []

        if chat.triggered and "prediction" in features and active_prediction:
            losing_team = fields.get("prev_possession") or state.possession
            if losing_team == active_prediction.offense:
                resolve = self._build_moment(
                    weight=0.85,
                    action="resolve_prediction",
                    message=self._message("resolve_prediction_no", state),
                    reason="possession change resolves prediction as loss",
                    cooldown_key="prediction_resolve",
                    payload={"winning_outcome_index": 1},
                )
                if resolve.triggered:
                    moments.append(resolve)

        return moments

    def _score_kill(
        self,
        state: SituationState,
        fields: dict[str, Any],
        features: set[str],
    ) -> list[ScoredMoment]:
        weight = 0.5
        score = fields.get("score", state.score)
        try:
            streak = int(fields.get("streak_count", 1) or 1)
        except (ValueError, TypeError):
            streak = 1
        if streak >= 3:
            weight += 0.3
        if state.game_category == "shooter" and (state.health is not None and state.health < 50):
            weight += 0.1

        key = "multi_kill" if streak >= 3 else "kill"
        message = self._message(key, state, score=score or "?", streak=streak)

        chat = self._build_moment(
            weight=min(weight, 1.0),
            action="chat",
            message=message,
            reason=key,
            cooldown_key="kill",
        )
        moments: list[ScoredMoment] = [chat] if chat.triggered else []

        if chat.triggered and "clip" in features and weight >= 0.8:
            clip = self._build_moment(
                weight=weight,
                action="clip",
                message=message,
                reason=f"{key} — clip",
                cooldown_key="clip",
            )
            if clip.triggered:
                moments.append(clip)

        return moments

    def _score_death(
        self,
        state: SituationState,
        fields: dict[str, Any],
        features: set[str],
    ) -> list[ScoredMoment]:
        chat = self._build_moment(
            weight=0.4,
            action="chat",
            message=self._message("death", state, health=fields.get("health", state.health)),
            reason="death",
            cooldown_key="death",
        )
        return [chat] if chat.triggered else []

    def _score_game_detected(self, state: SituationState) -> ScoredMoment:
        return self._build_moment(
            weight=0.4,
            action="chat",
            message=self._message("game_detected", state),
            reason="game detected",
            cooldown_key="game_detected",
        )

    def _score_visual_context(
        self,
        state: SituationState,
        payload: dict[str, Any],
        active_prediction: PredictionResult | None,
        features: set[str],
    ) -> list[ScoredMoment]:
        quarter = state.quarter or 0
        margin = abs((state.home_score or 0) - (state.away_score or 0))
        moments: list[ScoredMoment] = []

        # Late/close drive worth narrating
        if quarter >= 4 and margin <= 8 and self._is_red_zone(state) and state.down == 1:
            chat = self._build_moment(
                weight=0.6,
                action="chat",
                message=self._message("red_zone_drive", state, quarter=quarter),
                reason="late red-zone drive",
                cooldown_key="late_drive",
            )
            if chat.triggered:
                moments.append(chat)

        # Start a prediction when a promising drive begins
        if "prediction" in features and not active_prediction and self._is_start_prediction(state):
            pred = self._build_moment(
                weight=0.7,
                action="start_prediction",
                message=self._message("start_prediction", state),
                reason="red-zone, close game drive",
                cooldown_key="prediction_start",
                payload={
                    "title": "Score on this drive?",
                    "outcomes": ["Yes", "No"],
                    "window_s": 90,
                    "offense": state.possession,
                },
            )
            if pred.triggered:
                moments.append(pred)

        return moments

    def _scoring_team(self, fields: dict[str, Any], state: SituationState) -> str | None:
        """Determine which team just scored from outcome fields and state."""
        home = fields.get("home_score", state.home_score)
        away = fields.get("away_score", state.away_score)
        prev_home = fields.get("prev_home_score", state.home_score)
        prev_away = fields.get("prev_away_score", state.away_score)

        if home is None or away is None:
            return None

        try:
            home = int(home)
            away = int(away)
            prev_home = int(prev_home) if prev_home is not None else home
            prev_away = int(prev_away) if prev_away is not None else away
        except (ValueError, TypeError):
            return None

        if home > prev_home:
            return "home"
        if away > prev_away:
            return "away"
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # MESSAGE TEMPLATES
    # ──────────────────────────────────────────────────────────────────────────

    def _score_message(self, state: SituationState, home: Any, away: Any) -> str:
        extra = {"home_score": home or "?", "away_score": away or "?"}
        if state.controller.apm_5s > 80:
            extra["apm"] = int(state.controller.apm_5s)
        return self._message("score_changed", state, **extra)

    def _turnover_message(self, state: SituationState, fields: dict[str, Any]) -> str:
        return self._message("turnover", state)

    def _first_down_message(self, state: SituationState) -> str:
        return self._message("first_down", state)

    def _possession_message(self, state: SituationState, fields: dict[str, Any]) -> str:
        prev = fields.get("prev_possession")
        cur = fields.get("possession") or state.possession
        return self._message("possession_changed", state, prev_possession=prev or "", possession=cur or "")

    # ──────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────────────────────

    def _is_red_zone(self, state: SituationState) -> bool:
        # Look at field_position string, e.g. "opp 10" or "opponent 15".
        # If unavailable, fall back to a conservative false.
        pos = (state.field_position or "").lower()
        if not pos:
            return False

        match = re.search(r"opp(?:onent)?\s*(\d+)", pos)
        if match:
            yard = int(match.group(1))
            return yard <= 20

        if "own" in pos:
            return False

        return False

    def _is_start_prediction(self, state: SituationState) -> bool:
        # Promising drive: red zone, close game, 1st down
        margin = abs((state.home_score or 0) - (state.away_score or 0))
        return (
            self._is_red_zone(state)
            and state.down == 1
            and margin <= 14
            and (state.quarter or 0) >= 2
        )

    def _build_moment(
        self,
        weight: float,
        action: str,
        message: str,
        reason: str,
        cooldown_key: str,
        payload: dict[str, Any] | None = None,
    ) -> ScoredMoment:
        now = time.time()
        key = (action, cooldown_key)
        last = self._last_trigger.get(key, 0.0)

        cooldown_s = 30.0
        if action == "clip":
            cooldown_s = 60.0
        elif action in ("start_prediction", "resolve_prediction"):
            cooldown_s = 5.0

        if now - last < cooldown_s:
            return ScoredMoment(False, weight, "none", "", f"cooldown for {cooldown_key}", cooldown_key)

        self._last_trigger[key] = now
        return ScoredMoment(
            triggered=True,
            weight=weight,
            action=action,
            message=message,
            reason=reason,
            cooldown_key=cooldown_key,
            payload=payload or {},
        )
