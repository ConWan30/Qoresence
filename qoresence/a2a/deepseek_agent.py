"""DeepSeek chat agent via Quicksilver Pro for A2A.

Default: stub. Live when QORESENCE_A2A_DEEPSEEK=1 and API key set.
Reuses ClutchBot LLM path (deepseek-v4-flash @ quicksilverpro).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from qoresence.a2a.types import ChatProposal, SceneProposal
from qoresence.agents.llm_client import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    LLMConfig,
    QuicksilverLLMClient,
)

log = logging.getLogger(__name__)


class DeepSeekChatAgent:
    """Propose chat lines from a SceneProposal + situation."""

    def __init__(
        self,
        *,
        live: bool | None = None,
        model: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
        api_key_file: str | None = None,
        persona: str = "neutral",
    ) -> None:
        env_live = os.environ.get("QORESENCE_A2A_DEEPSEEK", "0").strip() in {"1", "true", "yes"}
        self.live = env_live if live is None else bool(live)
        self.persona = persona
        self.model = model or os.environ.get("QORESENCE_A2A_DEEPSEEK_MODEL", DEFAULT_MODEL)
        cfg = LLMConfig(
            enabled=self.live,
            provider="quicksilver",
            model=self.model,
            base_url=base_url,
            api_key=api_key,
            api_key_file=api_key_file
            or os.environ.get("QUICKSILVER_API_KEY_FILE")
            or (
                ".secrets/quicksilver_clutchbot.key"
                if __import__("pathlib").Path(".secrets/quicksilver_clutchbot.key").exists()
                else None
            ),
            timeout_s=8.0,
            max_tokens=120,
        )
        self._client = QuicksilverLLMClient(cfg)
        if self.live and not self._client.is_available():
            log.warning("A2A DeepSeek live but LLM unavailable — stub")
            self.live = False

    def propose_chat(
        self,
        scene: SceneProposal,
        *,
        situation: dict[str, Any] | None = None,
        path: str = "fast",
    ) -> ChatProposal:
        if not self.live:
            return self._stub(scene, path)
        try:
            return self._live(scene, situation or {}, path)
        except Exception as e:
            log.warning("DeepSeek chat live failed, stub: %s", e)
            return self._stub(scene, path)

    def _stub(self, scene: SceneProposal, path: str) -> ChatProposal:
        # Soft templates — no score digits
        if "armed" in (scene.tags or []) or scene.drive_phase == "armed":
            text = "Prediction window heating up — stay glued."
        elif "input_heat" in (scene.tags or []) or (scene.coupling or 0) >= 0.5:
            text = "Controller heat on a live drive — eyes up."
        elif scene.drive_phase == "pressure":
            text = "Pressure building — this possession matters."
        else:
            text = "Big moment energy — stay with it."
        # Blend scene summary lightly without digits
        if scene.summary and "score" not in scene.summary.lower():
            text = f"{text} {scene.summary}"[:140]
        return ChatProposal(
            text=text.strip()[:140],
            path=path if path in ("fast", "confirm") else "fast",
            persona=self.persona,
            soft_only=path != "confirm",
            based_on_scene=scene.summary[:80],
            model="stub-deepseek",
        )

    def _live(self, scene: SceneProposal, situation: dict[str, Any], path: str) -> ChatProposal:
        soft = path != "confirm"
        base = (
            "Rewrite as ONE Twitch chat line (<140 chars). "
            + (
                "SOFT PATH: no scores, no scorelines, no inventing digits. "
                if soft
                else "CONFIRM PATH: only use score digits if they match SituationState. "
            )
            + f"Scene: {scene.summary}. Tags: {scene.tags}."
        )
        text = self._client.enhance_message(
            situation=situation,
            event_type="a2a_scene",
            event_payload={"scene": scene.to_dict()},
            persona=self.persona,
            base_message=base,
        )
        if not text:
            return self._stub(scene, path)
        return ChatProposal(
            text=text[:140],
            path=path if path in ("fast", "confirm") else "fast",
            persona=self.persona,
            soft_only=soft,
            based_on_scene=scene.summary[:80],
            model=self.model,
        )
