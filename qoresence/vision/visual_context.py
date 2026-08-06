"""
Game-aware visual context returned by the VLM.

Modeled after QorTroller's Retina Visual Oracle (bridge/vapi_bridge/retina_visual_oracle.py).
The VLM is asked to return JSON; this module defines the structured dataclass and
football/shooter field sets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class GameState(str, Enum):
    MENU = "menu"
    LOBBY = "lobby"
    LOADING = "loading"
    GAMEPLAY = "gameplay"
    PAUSED = "paused"
    REPLAY = "replay"
    RESULTS = "results"
    SPECTATING = "spectating"
    CUTSCENE = "cutscene"
    UNKNOWN = "unknown"


class GameCategory(str, Enum):
    FOOTBALL = "football"
    SHOOTER = "shooter"
    UNKNOWN = "unknown"


@dataclass
class VisualContext:
    """Structured VLM output for a gameplay frame."""

    game_state: GameState = GameState.UNKNOWN
    game_title: str = ""
    game_category: GameCategory = GameCategory.UNKNOWN
    confidence: float = 0.0

    # Football / NCAA
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    quarter: Optional[int] = None
    down: Optional[int] = None
    yards_to_go: Optional[int] = None
    possession: Optional[str] = None  # "home" | "away" | team abbreviation
    clock_seconds: Optional[int] = None
    play_clock: Optional[int] = None
    play_type: Optional[str] = None
    field_position: Optional[str] = None
    down_distance_text: Optional[str] = None

    # Shooter / Call of Duty
    health: Optional[int] = None
    ammo: Optional[int] = None
    score: Optional[int] = None
    round_info: str = ""
    enemies_visible: int = 0
    is_combat: bool = False
    is_moving: bool = False

    # Frame quality
    has_screen_tearing: bool = False
    has_lag_indicator: bool = False
    frame_quality: str = "ok"  # ok|blurry|dark|overexposed

    # Provenance
    raw_response: str = ""
    frame_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "game_state": self.game_state.value,
            "game_title": self.game_title,
            "game_category": self.game_category.value,
            "confidence": self.confidence,
        }

        if self.game_category == GameCategory.FOOTBALL:
            d["football"] = {
                "home_score": self.home_score,
                "away_score": self.away_score,
                "quarter": self.quarter,
                "down": self.down,
                "yards_to_go": self.yards_to_go,
                "possession": self.possession,
                "clock_seconds": self.clock_seconds,
                "play_clock": self.play_clock,
                "play_type": self.play_type,
                "field_position": self.field_position,
                "down_distance_text": self.down_distance_text,
            }
        elif self.game_category == GameCategory.SHOOTER:
            d["shooter"] = {
                "health": self.health,
                "ammo": self.ammo,
                "score": self.score,
                "round_info": self.round_info,
                "enemies_visible": self.enemies_visible,
                "is_combat": self.is_combat,
                "is_moving": self.is_moving,
            }

        d["quality"] = {
            "has_screen_tearing": self.has_screen_tearing,
            "has_lag_indicator": self.has_lag_indicator,
            "frame_quality": self.frame_quality,
        }

        d["raw_response"] = self.raw_response[:500]
        d["frame_hash"] = self.frame_hash
        return d

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "VisualContext":
        """Build a VisualContext from a parsed VLM JSON response."""
        ctx = VisualContext()
        if not raw:
            return ctx

        def _state(s: Any) -> GameState:
            try:
                return GameState(str(s).lower().strip())
            except (ValueError, AttributeError):
                return GameState.UNKNOWN

        def _cat(s: Any) -> GameCategory:
            try:
                return GameCategory(str(s).lower().strip())
            except (ValueError, AttributeError):
                return GameCategory.UNKNOWN

        ctx.game_state = _state(raw.get("game_state"))
        ctx.game_title = str(raw.get("game_title", ""))
        ctx.game_category = _cat(raw.get("game_category"))
        ctx.confidence = float(raw.get("confidence", 0.0))

        # Football fields
        fb = raw.get("football") or {}
        ctx.home_score = _to_int(fb.get("home_score"))
        ctx.away_score = _to_int(fb.get("away_score"))
        ctx.quarter = _to_int(fb.get("quarter"))
        ctx.down = _to_int(fb.get("down"))
        ctx.yards_to_go = _to_int(fb.get("yards_to_go"))
        ctx.possession = _to_str(fb.get("possession"))
        ctx.clock_seconds = _to_int(fb.get("clock_seconds"))
        ctx.play_clock = _to_int(fb.get("play_clock"))
        ctx.play_type = _to_str(fb.get("play_type"))
        ctx.field_position = _to_str(fb.get("field_position"))
        ctx.down_distance_text = _to_str(fb.get("down_distance_text"))

        # Shooter fields
        sh = raw.get("shooter") or {}
        ctx.health = _to_int(sh.get("health"))
        ctx.ammo = _to_int(sh.get("ammo"))
        ctx.score = _to_int(sh.get("score"))
        ctx.round_info = str(sh.get("round_info", ""))
        ctx.enemies_visible = int(sh.get("enemies_visible", 0))
        ctx.is_combat = bool(sh.get("is_combat", False))
        ctx.is_moving = bool(sh.get("is_moving", False))

        # Quality / provenance
        qual = raw.get("quality") or {}
        ctx.has_screen_tearing = bool(qual.get("has_screen_tearing", False))
        ctx.has_lag_indicator = bool(qual.get("has_lag_indicator", False))
        ctx.frame_quality = str(qual.get("frame_quality", "ok"))

        return ctx


def _to_int(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _to_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def build_football_prompt() -> str:
    return (
        "Analyze this NCAA College Football 27 gameplay frame. "
        "Read the scoreboard and HUD carefully. "
        "Respond ONLY with valid JSON, no other text.\n\n"
        "{\"game_state\": \"menu|lobby|loading|gameplay|paused|replay|results|spectating|cutscene|unknown\", "
        "\"game_title\": \"\", "
        "\"game_category\": \"football\", "
        "\"home_score\": null, "
        "\"away_score\": null, "
        "\"quarter\": null, "
        "\"down\": null, "
        "\"yards_to_go\": null, "
        "\"possession\": null, "
        "\"clock_seconds\": null, "
        "\"play_clock\": null, "
        "\"play_type\": null, "
        "\"field_position\": null, "
        "\"down_distance_text\": null, "
        "\"quality\": {\"has_screen_tearing\": false, \"has_lag_indicator\": false, \"frame_quality\": \"ok\"}, "
        "\"confidence\": 0.0}"
    )


def build_shooter_prompt() -> str:
    return (
        "Analyze this Call of Duty gameplay frame. "
        "Read the HUD carefully. "
        "Respond ONLY with valid JSON, no other text.\n\n"
        "{\"game_state\": \"menu|lobby|loading|gameplay|paused|replay|results|spectating|cutscene|unknown\", "
        "\"game_title\": \"\", "
        "\"game_category\": \"shooter\", "
        "\"shooter\": {\"health\": null, \"ammo\": null, \"score\": null, \"round_info\": \"\", "
        "\"enemies_visible\": 0, \"is_combat\": false, \"is_moving\": false}, "
        "\"quality\": {\"has_screen_tearing\": false, \"has_lag_indicator\": false, \"frame_quality\": \"ok\"}, "
        "\"confidence\": 0.0}"
    )


def build_vlm_prompt(game_category: str) -> str:
    if game_category == "football":
        return build_football_prompt()
    return build_shooter_prompt()
