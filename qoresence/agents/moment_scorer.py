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
import math as _math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .helix_client import PredictionResult
from .situation_model import SituationState
from .win_probability import FootballWinProbability

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


class ClipWorthinessModel:
    """Lightweight logistic model for clip worthiness.

    Features expected (all optional, defaults to 0):
      - wp_swing: float (e.g. 0.0-0.5)
      - red_zone: float/int/bool (1 if in red zone else 0)
      - close_game: float/int/bool (1 if margin <=8 else 0)
      - apm: float (normalized, e.g. apm_5s / 100)
    Bias term is included via weights["bias"].
    """

    DEFAULT_WEIGHTS: dict[str, float] = {
        "wp_swing": 2.5,
        "red_zone": 0.8,
        "close_game": 0.6,
        "apm": 0.3,
        "bias": -0.8,
    }
    DEFAULT_PATH = Path("models/clip_worthiness.json")

    def __init__(
        self, model_path: str | Path | None = None, weights: dict[str, float] | None = None
    ):
        self.model_path: Path = Path(model_path) if model_path is not None else self.DEFAULT_PATH
        self.weights: dict[str, float] = (
            dict(weights) if weights is not None else dict(self.DEFAULT_WEIGHTS)
        )
        self.load()

    @staticmethod
    def _sigmoid(x: float) -> float:
        if x > 20:
            return 1.0
        if x < -20:
            return 0.0
        return 1.0 / (1.0 + _math.exp(-x))

    def predict(self, features: dict[str, float] | None = None) -> float:
        """Predict clip worthiness in [0,1] via sigmoid(weighted sum)."""
        features = features or {}

        def _f(k: str) -> float:
            v = features.get(k, 0)
            if isinstance(v, bool):
                return 1.0 if v else 0.0
            try:
                return float(v)
            except Exception:
                return 0.0

        wp_swing = _f("wp_swing")
        red_zone = _f("red_zone")
        close_game = _f("close_game")
        apm = _f("apm")
        w = self.weights
        logit = (
            wp_swing * w.get("wp_swing", 0)
            + red_zone * w.get("red_zone", 0)
            + close_game * w.get("close_game", 0)
            + apm * w.get("apm", 0)
            + w.get("bias", 0)
        )
        return self._sigmoid(logit)

    def load(self) -> None:
        """Load weights from JSON if file exists."""
        try:
            p = self.model_path
            if p.is_file():
                data = json.loads(p.read_text(encoding="utf-8"))
                w = data.get("weights") if isinstance(data, dict) and "weights" in data else data
                if isinstance(w, dict):
                    for k, v in w.items():
                        try:
                            self.weights[k] = float(v)
                        except Exception:
                            pass
        except Exception:
            pass

    def save(self) -> None:
        """Save current weights to JSON."""
        try:
            p = self.model_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"weights": self.weights}, indent=2), encoding="utf-8")
        except Exception as e:
            log.warning(f"ClipWorthinessModel save failed: {e}")


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
        },
    }

    def __init__(
        self,
        persona: str = "neutral",
        wp_enabled: bool = True,
        clip_model_path: str | Path | None = None,
        wp_swing_threshold: float = 0.12,
        learning_logger: Any | None = None,
    ):
        self.persona = persona
        self._templates = self._load_templates(persona)
        self._last_trigger: dict[tuple[str, str], float] = {}
        self._wp_swing_threshold: float = float(wp_swing_threshold)
        try:
            self._wp: FootballWinProbability | None = (
                FootballWinProbability() if wp_enabled else None
            )
        except Exception as e:
            log.warning(f"WP init failed: {e}")
            self._wp = None
        try:
            self._clip_model: ClipWorthinessModel = ClipWorthinessModel(clip_model_path)
        except Exception as e:
            log.warning(f"ClipWorthinessModel init failed: {e}")
            self._clip_model = ClipWorthinessModel(clip_model_path=None)

        self._learning_logger: Any | None = learning_logger

    def _is_football(self, state) -> bool:
        """Gate: FootballWinProbability only for football category."""
        cat = getattr(state, "game_category", None)
        if cat is None:
            return False
        # Handle Enum (GameCategory) or str
        if hasattr(cat, "value"):
            cat = cat.value
        return str(cat).lower().strip() == "football"

    def _maybe_wp_clip(self, state) -> tuple | None:
        if not getattr(self, "_wp", None):
            return None
        if not self._is_football(state):
            return None
        try:
            sd = {
                "quarter": state.quarter,
                "clock_seconds": state.game_clock_seconds,
                "down": state.down,
                "yards_to_go": state.yards_to_go,
                "field_position": state.field_position,
                "home_score": state.home_score,
                "away_score": state.away_score,
                "possession": state.possession,
            }
            r = self._wp.compute(sd)
            swing = float(r.get("wp_swing", 0.0))
            if abs(swing) < 0.02:
                return None
            msg = self._message("clip", state, wp_swing=f"{swing:+.2f}")
            m = self._build_moment(
                weight=min(0.95, 0.75 + abs(swing)),
                action="clip",
                message=msg or "Clutch clip incoming!",
                reason=f"wp_swing {swing:+.2f}",
                cooldown_key="wp_clip",
            )
            if not m.triggered:
                return None
            m.payload.update(
                {
                    "wp_swing": swing,
                    "win_prob": r.get("win_prob"),
                    "expected_points": r.get("expected_points"),
                }
            )
            return (m, swing)
        except Exception as e:
            import logging

            logging.getLogger(__name__).debug(f"_maybe_wp_clip failed: {e}")
            return None

    def _clip_gate(self, state, wp_swing: float) -> bool:
        if not self._is_football(state):
            return False
        try:
            import re

            pos = (state.field_position or "").lower()
            is_rz = 0.0
            if "opp" in pos:
                mm = re.search(r"opp(?:onent)?\s*(\d+)", pos)
                if mm and int(mm.group(1)) <= 20:
                    is_rz = 1.0
            hs = state.home_score
            aw = state.away_score
            try:
                margin = (
                    abs(int(hs or 0) - int(aw or 0)) if hs is not None and aw is not None else 10
                )
            except Exception:
                margin = 10
            close = 1.0 if margin <= 8 else 0.0
            apm = float(getattr(state.controller, "apm_5s", 0) or 0) / 120.0
            apm = max(0.0, min(1.0, apm))
            feats = {
                "wp_swing": float(wp_swing),
                "red_zone": is_rz,
                "close_game": close,
                "apm": apm,
            }
            score = self._clip_model.predict(feats) if getattr(self, "_clip_model", None) else 1.0
            return bool(
                score > 0.55
                or abs(float(wp_swing)) > float(getattr(self, "_wp_swing_threshold", 0.12))
            )
        except Exception:
            return True

    def _load_templates(self, persona: str) -> dict[str, str]:
        """Load persona templates from built-ins or a JSON file path."""
        if persona in self.DEFAULT_TEMPLATES:
            return self.DEFAULT_TEMPLATES[persona]

        path = Path(persona)
        if path.is_file():
            try:
                with open(path, encoding="utf-8") as f:
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
            scored = self._score_visual_context(
                state, event_payload or {}, active_prediction, features
            )
            wp_clip = self._maybe_wp_clip(state)
            if wp_clip and not any(m.action == "clip" and m.triggered for m in scored):
                if self._clip_gate(state, wp_clip[1]):
                    scored.append(wp_clip[0])
            if getattr(self, "_learning_logger", None) is not None and scored:
                try:
                    for _m in scored:
                        if _m.triggered:
                            self._learning_logger.log(
                                state,
                                _m,
                                label=None,
                                frame_hash=str((event_payload or {}).get("frame_hash", "")),
                                wp_swing=float(_m.payload.get("wp_swing", 0.0) or 0.0),
                            )
                except Exception:
                    pass
            return scored

        wp_clip_generic = self._maybe_wp_clip(state)
        if wp_clip_generic and wp_clip_generic[1] > self._wp_swing_threshold:
            if self._clip_gate(state, wp_clip_generic[1]):
                moments = [wp_clip_generic[0]]
                if getattr(self, "_learning_logger", None) is not None:
                    try:
                        for _m in moments:
                            self._learning_logger.log(
                                state,
                                _m,
                                label=None,
                                frame_hash=str((event_payload or {}).get("frame_hash", "")),
                                wp_swing=float(wp_clip_generic[1]),
                            )
                    except Exception:
                        pass
                return moments
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
                            "resolve_prediction_yes"
                            if winning_index == 0
                            else "resolve_prediction_no",
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

        try:
            _vc_clip_features = self._clip_features(state)
            _vc_clip_score = self._clip_model.predict(_vc_clip_features)
            for m in moments:
                if m.triggered and "clip_score" not in m.payload:
                    m.payload["clip_score"] = _vc_clip_score
                    m.payload["clip_features"] = _vc_clip_features
        except Exception:
            pass

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
        return self._message(
            "possession_changed", state, prev_possession=prev or "", possession=cur or ""
        )

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
            return ScoredMoment(
                False, weight, "none", "", f"cooldown for {cooldown_key}", cooldown_key
            )

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
