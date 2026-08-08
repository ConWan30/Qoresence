"""DeepSeek chat agent via Quicksilver Pro for A2A.

Default: stub. Live when QORESENCE_A2A_DEEPSEEK=1 and API key set.
Reuses ClutchBot LLM path (deepseek-v4-flash @ quicksilverpro).

Supports Trio P3 bidirectional tool calls: the agent can invoke
query-memory during chat proposal to reference recent events.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from qoresence.a2a.types import ChatProposal, SceneProposal
from qoresence.a2a.tools import ToolRegistry
from qoresence.a2a.tool_loop import run_tool_loop, parse_tool_calls
from qoresence.agents.llm_client import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    LLMConfig,
    QuicksilverLLMClient,
)

log = logging.getLogger(__name__)


class DeepSeekChatAgent:
    """Propose chat lines from a SceneProposal + situation.

    When a ToolRegistry is provided, the agent can call query-memory
    to enrich its commentary with recent event context.
    """

    def __init__(
        self,
        *,
        live: bool | None = None,
        model: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
        api_key_file: str | None = None,
        persona: str = "neutral",
        tools: ToolRegistry | None = None,
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
        self._tools = tools

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

        # Trio P3: Use query-memory to add recent event context to stub
        if self._tools:
            tool_context = self._stub_tool_enrichment()
            if tool_context:
                text = f"{text} {tool_context}"[:140]

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

    def _stub_tool_enrichment(self) -> str:
        """Use query-memory to find recent events for stub enrichment."""
        if not self._tools:
            return ""
        try:
            result = self._tools.call(
                "query-memory",
                event_type="outcome_event",
                seconds_back=120.0,
                limit=2,
            )
            events = result.get("events") or []
            if not events:
                return ""
            names = []
            for ev in events:
                payload = ev.get("payload") or {}
                name = payload.get("event_name")
                if name:
                    names.append(str(name))
            if names:
                return f"[Recent: {', '.join(names[:2])}]"
        except Exception as e:
            log.debug("DeepSeek stub tool enrichment failed: %s", e)
        return ""

    def _live(self, scene: SceneProposal, situation: dict[str, Any], path: str) -> ChatProposal:
        import json as _json

        soft = path != "confirm"

        # Trio P3: Pre-fetch recent events via query-memory tool
        memory_context = ""
        if self._tools:
            memory_context = self._live_tool_enrichment()

        base = (
            "Rewrite as ONE Twitch chat line (<140 chars). "
            + (
                "SOFT PATH: no scores, no scorelines, no inventing digits. "
                if soft
                else "CONFIRM PATH: only use score digits if they match SituationState. "
            )
            + f"Scene: {scene.summary}. Tags: {scene.tags}."
        )
        if memory_context:
            base += f" Recent events: {memory_context}."

        # Trio P3: Add tool definitions to prompt
        if self._tools:
            tool_defs = self._tools.list_tools()
            if tool_defs:
                base += (
                    "\nYou may request tool calls by including <tool_call>{\"name\":\"tool_name\",\"arguments\":{...}}</tool_call> "
                    "in your response. Available tools: "
                    + _json.dumps(tool_defs, separators=(",", ":"))[:300]
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

        # Trio P3: Run tool-call parse-execute loop if tool calls detected
        if self._tools and parse_tool_calls(text):
            def _llm_callback(tool_results_text: str) -> str:
                follow_base = base + "\n" + tool_results_text + "\nNow give your final chat line."
                return self._client.enhance_message(
                    situation=situation,
                    event_type="a2a_scene",
                    event_payload={"scene": scene.to_dict()},
                    persona=self.persona,
                    base_message=follow_base,
                ) or ""

            tool_output = run_tool_loop(text, self._tools, max_rounds=3, llm_callback=_llm_callback)
            text = tool_output.final_response

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

    def _live_tool_enrichment(self) -> str:
        """Fetch recent events via query-memory for live prompt enrichment."""
        if not self._tools:
            return ""
        try:
            result = self._tools.call(
                "query-memory",
                event_type="outcome_event",
                seconds_back=180.0,
                limit=4,
            )
            events = result.get("events") or []
            if not events:
                return ""
            summaries = []
            for ev in events:
                payload = ev.get("payload") or {}
                name = payload.get("event_name", ev.get("type", "event"))
                summaries.append(str(name))
            return ", ".join(summaries[:4])
        except Exception as e:
            log.debug("DeepSeek live tool enrichment failed: %s", e)
        return ""
