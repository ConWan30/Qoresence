"""Prompt synthesis for Foundry Reels.

Grounds LTX prompts in local Qoresence data: game profile, chapter label,
scoreboard state, and controller summary. Avoids EA/team/player likenesses.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qoresence.core.unified_config import GameProfile, GameProfileId, get_game_profile

log = logging.getLogger(__name__)

_BUILTIN_TEMPLATES: dict[str, dict[str, Any]] = {
    GameProfileId.NCAA_FOOTBALL_27.value: {
        "display_name": "NCAA College Football 27",
        "style": "cinematic sports broadcast",
        "negative": "blurry, distorted faces, watermark, text overlay, HUD, scoreboard",
        "templates": {
            "score_changed": "{quarter} quarter, {home_score}-{away_score}, {possession} team scores, dramatic sideline camera, stadium lights, 4K",
            "red_zone_entry": "Tense red-zone drive, {home_score}-{away_score}, crowd atmosphere, low-angle field shot",
            "touchdown": "Touchdown moment, {home_score}-{away_score}, celebration under stadium lights, sideline perspective",
            "clutch": "Clutch late-game moment, {home_score}-{away_score}, cinematic slow-motion feel, broadcast lighting",
            "default": "NCAA football broadcast, {quarter} quarter, {home_score}-{away_score}, intense game action, cinematic lighting",
        },
    },
    "_default": {
        "display_name": "gameplay",
        "style": "cinematic gameplay action",
        "negative": "blurry, distorted faces, watermark, text overlay, HUD",
        "templates": {
            "default": "Cinematic gameplay highlight, intense moment, dramatic lighting, 4K action shot",
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

    def __init__(self, template_dir: str | Path | None = None):
        self.template_dir = Path(template_dir) if template_dir else None
        self._templates: dict[str, dict[str, Any]] = dict(_BUILTIN_TEMPLATES)

    def _load_yaml_templates(self) -> None:
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
        template = templates.get(kind) or templates.get("default") or "{game} cinematic action, {chapter_label}, dramatic lighting"

        prompt = self._format_dict(template, ctx).strip()
        if not prompt:
            prompt = f"{ctx['game']} cinematic highlight, {ctx['chapter_label']}, dramatic lighting"

        style_prefix = style or tmpl.get("style") or "cinematic"
        if style_prefix and not prompt.lower().startswith(style_prefix.lower()):
            prompt = f"{style_prefix}, {prompt}"

        negative = tmpl.get("negative") or "blurry, distorted faces, watermark, text overlay, HUD"
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
        duration: int = 5,
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
