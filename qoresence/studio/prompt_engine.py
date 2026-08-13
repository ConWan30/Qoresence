"""Prompt synthesis for Foundry Reels.

Grounds LTX prompts in local Qoresence data: game profile, chapter label,
scoreboard state, and controller summary. Avoids EA/team/player likenesses.

Visual lock: film-grade 3D *graphics* (lighting, motion, finish) — not a
character redesign. Players stay football players matching the source frame.
LTX image-to-video has no negative_prompt field, so the lock leads the prompt.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qoresence.core.unified_config import GameProfile, GameProfileId, get_game_profile

log = logging.getLogger(__name__)

_DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parent / "prompts"

# Always leads the prompt. LTX follows this more than the scene clause.
STYLE_LOCK = (
    "cinematic 3D game-render, film-grade CG lighting and fluent motion, "
    "enhanced polished graphics, keep football players as football players "
    "matching the source frame, same helmets pads bodies and faces, "
    "no character redesign, not live-action footage, not sports documentary, "
    "not alien or Avatar-like faces, not oversized anime eyes"
)

_ANTI_LIVE_ACTION = (
    "live-action footage, documentary, ESPN broadcast, filmed camera, "
    "Avatar Na'vi faces, oversized anime eyes, alien features, character redesign"
)

_BUILTIN_TEMPLATES: dict[str, dict[str, Any]] = {
    GameProfileId.NCAA_FOOTBALL_27.value: {
        "display_name": "NCAA College Football 27",
        "style": "cinematic 3D game render",
        "negative": (
            f"{_ANTI_LIVE_ACTION}, blurry, distorted faces, watermark, "
            "text overlay, HUD, scoreboard"
        ),
        "templates": {
            "score_changed": (
                "{quarter} quarter, {home_score}-{away_score}, {possession} side scores, "
                "in-game sideline camera, rendered stadium, stylized 3D crowd bloom"
            ),
            "red_zone_entry": (
                "tense red-zone drive, {home_score}-{away_score}, "
                "low-angle 3D field shot, volumetric night light, animated crowd"
            ),
            "touchdown": (
                "touchdown beat, {home_score}-{away_score}, in-game celebration, "
                "rendered stadium lights, sideline camera"
            ),
            "clutch": (
                "clutch late-game beat, {home_score}-{away_score}, "
                "fluent 3D slow-motion, painterly stadium lighting"
            ),
            "default": (
                "college-football video-game world, {quarter} quarter, "
                "{home_score}-{away_score}, intense 3D animated action"
            ),
        },
    },
    "_default": {
        "display_name": "gameplay",
        "style": "cinematic 3D game render",
        "negative": f"{_ANTI_LIVE_ACTION}, blurry, distorted faces, watermark, text overlay, HUD",
        "templates": {
            "default": (
                "3D animated gameplay highlight, {chapter_label}, "
                "fluent motion, painterly rendered lighting"
            ),
        },
    },
}


@dataclass
class RenderPayload:
    """The payload sent to LTX for image-to-video."""

    prompt: str
    negative_prompt: str
    model: str
    duration: int
    resolution: str
    aspect_ratio: str
    fps: int | None
    generate_audio: bool
    image_uri: str = ""


class PromptEngine:
    """Build LTX prompts from local Qoresence context."""

    def __init__(self, template_dir: str | Path | None = _DEFAULT_TEMPLATE_DIR):
        self.template_dir = Path(template_dir) if template_dir else None
        self._templates: dict[str, dict[str, Any]] = dict(_BUILTIN_TEMPLATES)
        self._yaml_loaded = False

    def _load_yaml_templates(self) -> None:
        if self._yaml_loaded:
            return
        self._yaml_loaded = True
        if self.template_dir is None or not self.template_dir.exists():
            return
        try:
            import yaml
        except ImportError:
            return
        for path in sorted(self.template_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("profile_id"):
                    self._templates[str(data["profile_id"])] = data
            except Exception as e:
                log.debug("prompt template load failed: %s: %s", path, e)

    def _template_for(self, profile_id: str) -> dict[str, Any]:
        self._load_yaml_templates()
        return self._templates.get(profile_id) or self._templates.get("_default")

    def _format_dict(self, template: str, context: dict[str, Any]) -> str:
        # Simple string template, ignore missing keys.
        def _repl(m: re.Match[str]) -> str:
            key = m.group(1)
            return str(context.get(key) or "")

        return re.sub(r"\{(\w+)\}", _repl, template)

    def build_prompt(
        self,
        game_profile: GameProfile | str,
        chapter: dict[str, Any],
        situation: dict[str, Any] | None = None,
        buttons_summary: dict[str, int] | None = None,
        style: str | None = None,
    ) -> tuple[str, str]:
        """Return (prompt, negative_prompt) for a chapter."""
        profile_id = game_profile.profile_id.value if isinstance(game_profile, GameProfile) else str(game_profile)
        tmpl = self._template_for(profile_id)
        profile = get_game_profile(profile_id) if isinstance(game_profile, str) else game_profile

        ctx: dict[str, Any] = {
            "game": profile.display_name,
            "category": profile.category,
            "chapter_label": chapter.get("label") or "",
            "kind": chapter.get("kind") or "default",
            "t_s": chapter.get("t_s") or 0.0,
            "home_score": 0,
            "away_score": 0,
            "quarter": "",
            "possession": "",
            "kills": 0,
            "deaths": 0,
            "score": 0,
        }
        if situation:
            ctx.update(
                {
                    "home_score": situation.get("home_score") or 0,
                    "away_score": situation.get("away_score") or 0,
                    "quarter": situation.get("quarter") or "",
                    "possession": situation.get("possession") or "",
                    "kills": situation.get("kills") or 0,
                    "deaths": situation.get("deaths") or 0,
                    "score": situation.get("score") or 0,
                }
            )

        kind = str(chapter.get("kind") or "default")
        templates = tmpl.get("templates") or {}
        template = (
            templates.get(kind)
            or templates.get("default")
            or "{game} 3D animated action, {chapter_label}, painterly lighting"
        )

        scene = self._format_dict(template, ctx).strip()
        if not scene:
            scene = f"{ctx['game']} 3D animated highlight, {ctx['chapter_label']}"

        flavor = (style or tmpl.get("style") or "cinematic 3D game render").strip()
        parts = [STYLE_LOCK]
        if flavor and flavor.lower() not in STYLE_LOCK.lower():
            parts.append(flavor)
        parts.append(scene)
        prompt = ", ".join(parts)

        negative = tmpl.get("negative") or f"{_ANTI_LIVE_ACTION}, blurry, distorted faces, watermark"
        return prompt, negative

    def build_payload(
        self,
        game_profile: GameProfile | str,
        chapter: dict[str, Any],
        situation: dict[str, Any] | None = None,
        buttons_summary: dict[str, int] | None = None,
        *,
        style: str | None = None,
        model: str = "ltx-2-3-pro",
        duration: int = 6,
        resolution: str = "1920x1080",
        aspect_ratio: str = "16:9",
        fps: int | None = None,
        generate_audio: bool = False,
    ) -> RenderPayload:
        """Build a full RenderPayload for LtxClient."""
        prompt, negative = self.build_prompt(
            game_profile, chapter, situation, buttons_summary, style=style
        )
        return RenderPayload(
            prompt=prompt,
            negative_prompt=negative,
            model=model,
            duration=duration,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            fps=fps,
            generate_audio=generate_audio,
        )
