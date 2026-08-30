"""Structured visual context extracted from HDMI frames.

This is the output of the visual understanding pipeline:
    HDMI frame → YOLO + OCR + heuristics → VisualContext

The VisualContext is a compact, structured representation of what's
happening on screen. It feeds into the Situation Model (Layer 2) and
the Cognitive Cortex (Layer 3).

This is NOT a raw frame or embedding. It's a parsed understanding
of the game state that an LLM can consume as text.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# Scene types the visual pipeline can identify
SCENE_TYPES = (
    "gameplay",
    "menu",
    "scoreboard",
    "loading",
    "cutscene",
    "unknown",
)

# Game genres for context-aware analysis
GAME_GENRES = (
    "football",
    "soccer",
    "basketball",
    "hockey",
    "racing",
    "fighting",
    "shooter",
    "moba",
    "unknown",
)

# Football-specific play types
FOOTBALL_PLAYS = (
    "run",
    "pass",
    "punt",
    "field_goal",
    "kickoff",
    "kneel",
    "unknown",
)

# Football field zones
FIELD_ZONES = (
    "own_endzone",
    "own_redzone",
    "own_territory",
    "midfield",
    "opp_territory",
    "opp_redzone",
    "opp_endzone",
    "unknown",
)


@dataclass
class DetectedObject:
    """A single object detected by YOLO."""

    label: str
    confidence: float
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0
    track_id: Optional[int] = None

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2

    @property
    def area(self) -> float:
        return max(0, self.x2 - self.x1) * max(0, self.y2 - self.y1)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DetectedObject:
        return cls(
            label=str(data.get("label", "unknown")),
            confidence=float(data.get("confidence", 0.0)),
            x1=float(data.get("x1", 0.0)),
            y1=float(data.get("y1", 0.0)),
            x2=float(data.get("x2", 0.0)),
            y2=float(data.get("y2", 0.0)),
            track_id=data.get("track_id"),
        )


@dataclass
class VisualContext:
    """Structured understanding of a single HDMI frame.

    This is what the visual pipeline produces. Every field is optional
    because not every frame has all information available.
    """

    # Temporal
    timestamp: float = 0.0
    frame_id: int = 0

    # Scene classification
    scene_type: str = "unknown"
    scene_confidence: float = 0.0
    game_genre: str = "unknown"
    game_title: str = ""

    # Detected objects (from YOLO)
    objects: list[DetectedObject] = field(default_factory=list)
    object_count: int = 0

    # Text extracted (from OCR)
    ocr_text: list[str] = field(default_factory=list)
    score_home: Optional[int] = None
    score_away: Optional[int] = None
    clock: str = ""
    quarter: Optional[int] = None
    down: Optional[int] = None
    distance: Optional[int] = None
    yard_line: Optional[int] = None

    # Seeing-path receipt: why the board is held or live.
    # "" = no hold (digits may be live). Non-empty = hold reason.
    board_why: str = ""

    # Spatial understanding
    field_zone: str = "unknown"
    ball_visible: bool = False
    ball_x: Optional[float] = None
    ball_y: Optional[float] = None
    player_count: int = 0

    # Football-specific
    play_type: str = "unknown"
    formation: str = ""
    possession: str = ""  # "home" or "away"

    # Motion
    motion_level: float = 0.0  # 0=static, 1=high motion
    camera_cut: bool = False

    # Quality
    confidence: float = 0.0
    source: str = "pipeline"  # "pipeline", "vlm", "hybrid"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["objects"] = [o.to_dict() if hasattr(o, "to_dict") else o for o in self.objects]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VisualContext:
        objects = [DetectedObject.from_dict(o) if isinstance(o, dict) else o
                    for o in data.get("objects", [])]
        return cls(
            timestamp=float(data.get("timestamp", 0.0)),
            frame_id=int(data.get("frame_id", 0)),
            scene_type=str(data.get("scene_type", "unknown")),
            scene_confidence=float(data.get("scene_confidence", 0.0)),
            game_genre=str(data.get("game_genre", "unknown")),
            game_title=str(data.get("game_title", "")),
            objects=objects,
            object_count=int(data.get("object_count", len(objects))),
            ocr_text=list(data.get("ocr_text", [])),
            score_home=data.get("score_home"),
            score_away=data.get("score_away"),
            clock=str(data.get("clock", "")),
            quarter=data.get("quarter"),
            down=data.get("down"),
            distance=data.get("distance"),
            yard_line=data.get("yard_line"),
            board_why=str(data.get("board_why", "") or ""),
            field_zone=str(data.get("field_zone", "unknown")),
            ball_visible=bool(data.get("ball_visible", False)),
            ball_x=data.get("ball_x"),
            ball_y=data.get("ball_y"),
            player_count=int(data.get("player_count", 0)),
            play_type=str(data.get("play_type", "unknown")),
            formation=str(data.get("formation", "")),
            possession=str(data.get("possession", "")),
            motion_level=float(data.get("motion_level", 0.0)),
            camera_cut=bool(data.get("camera_cut", False)),
            confidence=float(data.get("confidence", 0.0)),
            source=str(data.get("source", "pipeline")),
        )

    def to_prompt_text(self) -> str:
        """Render as compact text for LLM consumption."""
        parts = []

        # Scene
        if self.scene_type != "unknown":
            parts.append(f"Scene: {self.scene_type}")
        if self.game_genre != "unknown":
            parts.append(f"Genre: {self.game_genre}")
        if self.game_title:
            parts.append(f"Game: {self.game_title}")

        # Score
        if self.score_home is not None and self.score_away is not None:
            parts.append(f"Score: {self.score_home}-{self.score_away}")
        if self.clock:
            parts.append(f"Clock: {self.clock}")
        if self.quarter:
            parts.append(f"Q{self.quarter}")
        if self.down and self.distance:
            parts.append(f"{self.down} & {self.distance}")
        if self.yard_line is not None:
            parts.append(f"Ball on {self.yard_line}")

        # Objects
        if self.objects:
            labels = {}
            for obj in self.objects:
                labels[obj.label] = labels.get(obj.label, 0) + 1
            obj_str = ", ".join(f"{count} {label}" for label, count in labels.items())
            parts.append(f"Visible: {obj_str}")
        elif self.object_count:
            parts.append(f"Objects: {self.object_count}")

        # Spatial
        if self.field_zone != "unknown":
            parts.append(f"Field: {self.field_zone}")
        if self.ball_visible:
            parts.append("Ball visible")
        if self.play_type != "unknown":
            parts.append(f"Play: {self.play_type}")
        if self.formation:
            parts.append(f"Formation: {self.formation}")
        if self.possession:
            parts.append(f"Possession: {self.possession}")

        # Motion
        if self.motion_level > 0.7:
            parts.append("High motion")
        elif self.motion_level < 0.2 and self.motion_level > 0:
            parts.append("Static")
        if self.camera_cut:
            parts.append("Camera cut")

        # OCR leftovers
        if self.ocr_text:
            remaining = [t for t in self.ocr_text if t not in str(parts)]
            if remaining:
                parts.append(f"Text: {', '.join(remaining[:5])}")

        return " | ".join(parts) if parts else "No visual context"

    def summary(self) -> str:
        """One-line summary."""
        return self.to_prompt_text()


def build_football_prompt(ctx: VisualContext) -> str:
    """Build a football-specific VLM prompt from visual context."""
    score = ""
    if ctx.score_home is not None and ctx.score_away is not None:
        score = f"Score is {ctx.score_home}-{ctx.score_away}. "
    clock = f"Clock: {ctx.clock}. " if ctx.clock else ""
    down = ""
    if ctx.down and ctx.distance:
        down = f"{ctx.down}rd and {ctx.distance}. " if ctx.down == 3 else f"{ctx.down} and {ctx.distance}. "
    field = f"Ball is at the {ctx.field_zone}. " if ctx.field_zone != "unknown" else ""
    play = f"This looks like a {ctx.play_type} play. " if ctx.play_type != "unknown" else ""

    return (
        f"This is a football game. {score}{clock}{down}{field}{play}"
        "Analyze this frame. Identify: formation, play type, "
        "what's happening right now, and any notable observations. "
        "Be specific and concise."
    )


def build_shooter_prompt(ctx: VisualContext) -> str:
    """Build a shooter-specific VLM prompt from visual context."""
    return (
        "This is a first-person shooter. Analyze this frame. "
        "Identify: location/map, enemies visible, health/ammo status, "
        "what's happening, and any tactical observations. "
        "Be specific and concise."
    )


# ---------------------------------------------------------------------------
# VLM-as-primary visual understanding (replaces YOLO+OCR+heuristics)
# ---------------------------------------------------------------------------

FOOTBALL_VLM_PROMPT = """You are watching a live Madden NFL football game on screen.
Analyze this frame and return ONLY a JSON object with these fields:
{
    "scene_type": "gameplay" or "menu" or "scoreboard" or "loading" or "replay" or "celebration",
    "play_phase": "pre_snap" or "huddle_offense" or "huddle_defense" or "snap" or "running" or "passing" or "ball_in_air" or "tackle" or "whistle" or "replay" or "between_plays",
    "formation": "shotgun" or "under_center" or "pistol" or "i_form" or "singleback" or "empty" or "goal_line" or "wildcat" or "unknown",
    "play_type": "run" or "pass" or "play_action" or "screen" or "rpo" or "punt" or "field_goal" or "kickoff" or "kneel" or "unknown",
    "ball_visible": true or false,
    "ball_carrier_visible": true or false,
    "qb_visible": true or false,
    "receivers_visible": number,
    "defenders_near_ball": number,
    "field_zone": "own_endzone" or "own_redzone" or "own_territory" or "midfield" or "opp_territory" or "opp_redzone" or "opp_endzone",
    "hash_mark": "left" or "middle" or "right",
    "score_home": number or null,
    "score_away": number or null,
    "quarter": 1-4 or "OT" or null,
    "clock": "MM:SS" or null,
    "down": 1-4 or null,
    "distance": number or null,
    "yard_line": number or null,
    "possession": "home" or "away" or null,
    "motion_level": "static" or "low" or "medium" or "high",
    "camera_angle": "broadcast" or "sideline" or "endzone" or "all22" or "replay" or "unknown",
    "notable": "brief description of anything unusual or important"
}
Return ONLY the JSON. No markdown, no explanation."""


SHOOTER_VLM_PROMPT = """You are watching a first-person shooter game on screen.
Analyze this frame and return ONLY a JSON object:
{
    "scene_type": "gameplay" or "menu" or "map" or "killcam" or "loading" or "scoreboard",
    "location": "description of the area",
    "enemies_visible": number,
    "teammates_visible": number,
    "health": number or null,
    "ammo": number or null,
    "weapon": "weapon name or unknown",
    "in_combat": true or false,
    "notable": "brief description"
}
Return ONLY the JSON. No markdown, no explanation."""


def parse_vlm_visual_response(raw: str, timestamp: float = 0.0) -> VisualContext:
    """Parse a VLM JSON response into a VisualContext."""
    import json as _json
    import re

    text = raw.strip()
    # Extract JSON from markdown fences if present
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if fence:
        text = fence.group(1).strip()
    # Find the JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return VisualContext(timestamp=timestamp, source="vlm", confidence=0.0)

    try:
        data = _json.loads(text[start:end + 1])
    except (_json.JSONDecodeError, ValueError):
        return VisualContext(timestamp=timestamp, source="vlm", confidence=0.0)

    motion_map = {"static": 0.1, "low": 0.3, "medium": 0.6, "high": 0.9}
    motion = data.get("motion_level", "")
    if isinstance(motion, str):
        motion = motion_map.get(motion.lower(), 0.0)
    else:
        motion = float(motion) if motion else 0.0

    return VisualContext(
        timestamp=timestamp,
        scene_type=str(data.get("scene_type", "unknown")),
        scene_confidence=0.8,
        game_genre="football" if "play_phase" in data or "formation" in data else "unknown",
        score_home=data.get("score_home"),
        score_away=data.get("score_away"),
        clock=str(data.get("clock") or ""),
        quarter=data.get("quarter") if isinstance(data.get("quarter"), int) else None,
        down=data.get("down"),
        distance=data.get("distance"),
        yard_line=data.get("yard_line"),
        field_zone=str(data.get("field_zone", "unknown")),
        ball_visible=bool(data.get("ball_visible", False)),
        play_type=str(data.get("play_type", "unknown")),
        formation=str(data.get("formation", "")),
        possession=str(data.get("possession") or ""),
        motion_level=motion,
        camera_cut=str(data.get("play_phase", "")) == "replay",
        confidence=0.8,
        source="vlm",
    )
