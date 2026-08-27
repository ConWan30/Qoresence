"""
Game-aware visual context returned by the VLM.

Modeled after QorTroller's Retina Visual Oracle (bridge/vapi_bridge/retina_visual_oracle.py).
The VLM is asked to return JSON; this module defines the structured dataclass and
football/shooter field sets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class GameState(StrEnum):
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


class GameCategory(StrEnum):
    FOOTBALL = "football"
    SHOOTER = "shooter"
    UNKNOWN = "unknown"


@dataclass
class VisualContext:
    """Structured VLM output for a gameplay frame."""

    game_state: GameState = GameState.UNKNOWN
    game_title: str = ""
    game_profile: str = ""  # profile id, e.g. "ncaa_football_27"
    game_category: GameCategory = GameCategory.UNKNOWN
    confidence: float = 0.0

    # Football / NCAA
    home_score: int | None = None
    away_score: int | None = None
    # True when the HOME team's score appears on the left side of the scoreboard.
    # Default/None means away-left / home-right (the most common broadcast layout).
    home_left: bool | None = None
    quarter: int | None = None
    down: int | None = None
    yards_to_go: int | None = None
    possession: str | None = None  # "home" | "away" | team abbreviation
    clock_seconds: int | None = None
    play_clock: int | None = None
    play_type: str | None = None
    field_position: str | None = None
    down_distance_text: str | None = None
    home_team_raw: str | None = None
    away_team_raw: str | None = None
    home_team: str | None = None
    away_team: str | None = None
    home_team_name: str | None = None
    away_team_name: str | None = None
    home_color: str | None = None
    away_color: str | None = None
    home_logo: str | None = None
    away_logo: str | None = None
    home_hex: str | None = None
    away_hex: str | None = None
    player_name_raw: str | None = None
    player_jersey: int | None = None
    on_screen_player: str | None = None
    on_screen_player_team: str | None = None
    on_screen_player_jersey: int | None = None
    on_screen_player_pos: str | None = None
    nameplate_ambiguous: bool = False
    nameplate_match: str | None = None
    roster_loaded: bool = False

    # Shooter / Call of Duty
    health: int | None = None
    ammo: int | None = None
    score: int | None = None
    kills: int | None = None
    deaths: int | None = None
    round_info: str = ""
    enemies_visible: int = 0
    is_combat: bool = False
    is_moving: bool = False

    # Frame quality
    has_screen_tearing: bool = False
    has_lag_indicator: bool = False
    frame_quality: str = "ok"  # ok|blurry|dark|overexposed

    # Score provenance: True when the scoreboard VLM referee force-locked the
    # score (overrides OCR). Downstream gates must trust VLM-locked scores even
    # when they look like "drops" relative to a prior bad OCR lock (e.g. 20-20
    # corrected to 20-0). See engineering invariants #4/#5.
    score_vlm_locked: bool = False
    confirm_ticket_id: str = ""

    # Provenance
    raw_response: str = ""
    frame_hash: str = ""

    # VLM client metadata
    model: str = ""
    latency_ms: float = 0.0
    details: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize string/enum inputs."""
        raw_state = ""
        if isinstance(self.game_state, str):
            raw_state = self.game_state.lower().strip()
            if raw_state in {"football", "shooter"}:
                try:
                    self.game_category = GameCategory(raw_state)
                except ValueError:
                    self.game_category = GameCategory.UNKNOWN
                self.game_state = GameState.GAMEPLAY
            else:
                try:
                    self.game_state = GameState(raw_state)
                except ValueError:
                    self.game_state = GameState.UNKNOWN
        if isinstance(self.game_category, str):
            try:
                self.game_category = GameCategory(self.game_category.lower().strip())
            except ValueError:
                self.game_category = GameCategory.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "game_state": self.game_state.value,
            "game_title": self.game_title,
            "game_profile": self.game_profile,
            "game_category": self.game_category.value,
            "confidence": self.confidence,
        }

        if self.game_category == GameCategory.FOOTBALL:
            d["football"] = {
                "home_score": self.home_score,
                "away_score": self.away_score,
                "home_left": self.home_left,
                "quarter": self.quarter,
                "down": self.down,
                "yards_to_go": self.yards_to_go,
                "possession": self.possession,
                "clock_seconds": self.clock_seconds,
                "play_clock": self.play_clock,
                "play_type": self.play_type,
                "field_position": self.field_position,
                "down_distance_text": self.down_distance_text,
                "home_team_raw": self.home_team_raw,
                "away_team_raw": self.away_team_raw,
                "home_team": self.home_team,
                "away_team": self.away_team,
                "home_team_name": self.home_team_name,
                "away_team_name": self.away_team_name,
                "home_color": self.home_color,
                "away_color": self.away_color,
                "home_logo": self.home_logo,
                "away_logo": self.away_logo,
                "home_hex": self.home_hex,
                "away_hex": self.away_hex,
                "player_name_raw": self.player_name_raw,
                "player_jersey": self.player_jersey,
                "on_screen_player": self.on_screen_player,
                "on_screen_player_team": self.on_screen_player_team,
                "on_screen_player_jersey": self.on_screen_player_jersey,
                "on_screen_player_pos": self.on_screen_player_pos,
                "nameplate_ambiguous": bool(self.nameplate_ambiguous),
                "nameplate_match": self.nameplate_match,
                "roster_loaded": bool(self.roster_loaded),
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
        d["model"] = self.model
        d["latency_ms"] = self.latency_ms
        d["details"] = self.details
        d["score_vlm_locked"] = self.score_vlm_locked
        d["confirm_ticket_id"] = self.confirm_ticket_id
        
        # Include visual_phase at top level for convenience if present in details
        if isinstance(self.details, dict) and "visual_phase" in self.details:
            d["visual_phase"] = self.details.get("visual_phase")
        
        return d

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> VisualContext:
        """Build a VisualContext from a parsed VLM JSON response.

        Accepts both flat VLM output (legacy/LLM prompt shape) and the nested
        ``to_dict`` round-trip shape. Also normalizes legacy state names such
        as ``"football"`` / ``"shooter"`` into proper ``game_state`` +
        ``game_category`` pairs.
        """
        ctx = VisualContext()
        if not raw:
            return ctx

        def _state(s: Any) -> GameState:
            if s is None:
                return GameState.UNKNOWN
            try:
                return GameState(str(s).lower().strip())
            except (ValueError, AttributeError):
                return GameState.UNKNOWN

        def _cat(s: Any) -> GameCategory:
            if s is None:
                return GameCategory.UNKNOWN
            try:
                return GameCategory(str(s).lower().strip())
            except (ValueError, AttributeError):
                return GameCategory.UNKNOWN

        raw_state = str(raw.get("game_state", "")).lower().strip()
        category = _cat(raw.get("game_category"))

        # Legacy: VLM sometimes returns game_state="football"/"shooter"/"menu".
        if raw_state in {"football", "shooter"}:
            category = _cat(raw_state)
            ctx.game_state = GameState.GAMEPLAY
        else:
            ctx.game_state = _state(raw_state) if raw_state else GameState.UNKNOWN

        ctx.game_title = str(raw.get("game_title", ""))
        ctx.game_profile = str(raw.get("game_profile", ""))
        ctx.game_category = category
        ctx.confidence = float(raw.get("confidence", 0.0))

        # Football fields: support nested "football" block or flat top-level keys
        fb = raw.get("football")
        if fb is None and (
            category == GameCategory.FOOTBALL
            or ctx.game_title.lower() in {"ncaa football 27", "ncaa"}
        ):
            fb = raw
        else:
            fb = fb or {}

        ctx.home_score = _to_int(fb.get("home_score"))
        ctx.away_score = _to_int(fb.get("away_score"))
        ctx.home_left = _to_bool(fb.get("home_left"))
        ctx.quarter = _to_int(fb.get("quarter"))
        ctx.down = _to_int(fb.get("down"))
        ctx.yards_to_go = _to_int(fb.get("yards_to_go"))
        ctx.possession = _to_str(fb.get("possession"))
        ctx.clock_seconds = _to_int(fb.get("clock_seconds"))
        ctx.play_clock = _to_int(fb.get("play_clock"))
        ctx.play_type = _to_str(fb.get("play_type"))
        ctx.field_position = _to_str(fb.get("field_position"))
        ctx.down_distance_text = _to_str(fb.get("down_distance_text"))
        ctx.home_team_raw = _to_str(fb.get("home_team_raw") or fb.get("home_team"))
        ctx.away_team_raw = _to_str(fb.get("away_team_raw") or fb.get("away_team"))
        ctx.home_team = _to_str(fb.get("home_team"))
        ctx.away_team = _to_str(fb.get("away_team"))
        ctx.home_team_name = _to_str(fb.get("home_team_name"))
        ctx.away_team_name = _to_str(fb.get("away_team_name"))
        ctx.home_color = _to_str(fb.get("home_color"))
        ctx.away_color = _to_str(fb.get("away_color"))
        ctx.home_logo = _to_str(fb.get("home_logo"))
        ctx.away_logo = _to_str(fb.get("away_logo"))
        ctx.home_hex = _to_str(fb.get("home_hex"))
        ctx.away_hex = _to_str(fb.get("away_hex"))
        ctx.player_name_raw = _to_str(fb.get("player_name") or fb.get("player_name_raw"))
        ctx.player_jersey = _to_int(fb.get("player_jersey"))
        ctx.nameplate_ambiguous = bool(fb.get("nameplate_ambiguous") or raw.get("nameplate_ambiguous"))
        # Resolved names come from the local NFL roster — never trust the model
        # to invent a club. Raw HUD strings are matched or dropped.
        try:
            from qoresence.profiles.nfl_roster import apply_roster_to_context, is_madden_profile

            if is_madden_profile(ctx.game_profile) or is_madden_profile(raw.get("game_profile")):
                apply_roster_to_context(
                    ctx,
                    {
                        "home_team_raw": ctx.home_team_raw,
                        "away_team_raw": ctx.away_team_raw,
                        "player_name": ctx.player_name_raw,
                        "player_jersey": ctx.player_jersey,
                        "game_profile": ctx.game_profile or raw.get("game_profile"),
                    },
                )
        except Exception:
            pass

        # Shooter fields: support nested "shooter" block or flat top-level keys
        sh = raw.get("shooter")
        if sh is None and category == GameCategory.SHOOTER:
            sh = raw
        else:
            sh = sh or {}

        ctx.health = _to_int(sh.get("health"))
        ctx.ammo = _to_int(sh.get("ammo"))
        ctx.score = _to_int(sh.get("score"))
        # kills/deaths: new fields (also accept legacy flat score / details)
        ctx.kills = (
            _to_int(sh.get("kills")) if sh.get("kills") is not None else _to_int(raw.get("kills"))
        )
        ctx.deaths = (
            _to_int(sh.get("deaths"))
            if sh.get("deaths") is not None
            else _to_int(raw.get("deaths"))
        )
        # fallback: details.kills/deaths or score as kills
        if (
            ctx.kills is None
            and isinstance(ctx.details, dict)
            and ctx.details.get("kills") is not None
        ):
            ctx.kills = _to_int(ctx.details.get("kills"))
        if (
            ctx.deaths is None
            and isinstance(ctx.details, dict)
            and ctx.details.get("deaths") is not None
        ):
            ctx.deaths = _to_int(ctx.details.get("deaths"))
        ctx.round_info = str(sh.get("round_info", ""))
        ctx.enemies_visible = int(sh.get("enemies_visible", 0))
        ctx.is_combat = bool(sh.get("is_combat", False))
        ctx.is_moving = bool(sh.get("is_moving", False))

        # Quality / provenance
        qual = raw.get("quality") or {}
        ctx.has_screen_tearing = bool(qual.get("has_screen_tearing", False))
        ctx.has_lag_indicator = bool(qual.get("has_lag_indicator", False))
        ctx.frame_quality = str(qual.get("frame_quality", "ok"))

        ctx.raw_response = str(raw.get("raw_response", ""))[:500]
        ctx.frame_hash = str(raw.get("frame_hash", ""))
        ctx.model = str(raw.get("model", ""))
        ctx.latency_ms = float(raw.get("latency_ms", 0.0))
        ctx.details = raw.get("details") or {}
        ctx.score_vlm_locked = bool(raw.get("score_vlm_locked", False))
        ctx.confirm_ticket_id = str(raw.get("confirm_ticket_id") or "")

        # Extract visual_phase from top-level or details and store in details for consistency
        visual_phase = raw.get("visual_phase")
        if visual_phase is not None:
            # Store in details for consistent access pattern
            if not isinstance(ctx.details, dict):
                ctx.details = {}
            ctx.details["visual_phase"] = str(visual_phase).strip().lower() if visual_phase else None
        elif isinstance(ctx.details, dict) and "visual_phase" in ctx.details:
            # Already in details, normalize it
            vp = ctx.details.get("visual_phase")
            ctx.details["visual_phase"] = str(vp).strip().lower() if vp else None

        return ctx


def _to_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _to_bool(v: Any) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off", "", "none", "null"}:
        return False
    return None


def _to_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def build_football_prompt() -> str:
    return (
        "Analyze this EA College Football 27 or Madden NFL 27 gameplay frame. "
        "Read THIS match's primary scorebug / HUD only. "
        "IGNORE the bottom ticker or crawl of other games' scores. "
        "Report home_score as the HOME team's score and away_score as the AWAY team's score, "
        "regardless of which side of the scoreboard they appear on. "
        "If the team names or HOME/AWAY labels clearly show the HOME team is on the LEFT, "
        "set home_left to true; otherwise set it to false or null. "
        "Possession should be 'home' when the team on the right has the ball, 'away' when the team on the left has it. "
        "Identify the visual_phase of play from this allowlist: "
        '"huddle_offense", "huddle_defense", "snap", "running", "passing", "ball_in_air", '
        '"coverage", "defense_pursuit", "defense_engaged", "blocking", "player_locked_receiver". '
        "If the phase is unclear or not in the allowlist, set visual_phase to null. "
        "Respond ONLY with valid JSON, no other text.\n\n"
        '{"game_state": "menu|lobby|loading|gameplay|paused|replay|results|spectating|cutscene|unknown", '
        '"game_title": "", '
        '"game_profile": "", '
        '"game_category": "football", '
        '"home_score": null, '
        '"away_score": null, '
        '"home_left": null, '
        '"quarter": null, '
        '"down": null, '
        '"yards_to_go": null, '
        '"possession": null, '
        '"clock_seconds": null, '
        '"play_clock": null, '
        '"play_type": null, '
        '"field_position": null, '
        '"down_distance_text": null, '
        '"home_team": null, '
        '"away_team": null, '
        '"player_name": null, '
        '"player_jersey": null, '
        '"visual_phase": null, '
        '"quality": {"has_screen_tearing": false, "has_lag_indicator": false, "frame_quality": "ok"}, '
        '"confidence": 0.0}'
    )


def build_shooter_prompt() -> str:
    return (
        "Analyze this Call of Duty gameplay frame. "
        "Read the HUD carefully. "
        "Respond ONLY with valid JSON, no other text.\n\n"
        '{"game_state": "menu|lobby|loading|gameplay|paused|replay|results|spectating|cutscene|unknown", '
        '"game_title": "", '
        '"game_profile": "", '
        '"game_category": "shooter", '
        '"shooter": {"health": null, "ammo": null, "score": null, "round_info": "", '
        '"enemies_visible": 0, "is_combat": false, "is_moving": false}, '
        '"quality": {"has_screen_tearing": false, "has_lag_indicator": false, "frame_quality": "ok"}, '
        '"confidence": 0.0}'
    )


def build_vlm_prompt(game_category: str) -> str:
    if game_category == "football":
        return build_football_prompt()
    return build_shooter_prompt()
