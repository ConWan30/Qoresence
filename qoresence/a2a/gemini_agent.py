"""Gemini scene agent via Quicksilver Pro (OpenAI-compatible vision/chat).

Default: stub (no network). Live when QORESENCE_A2A_GEMINI=1 and API key set.
Model default: gemini-3.5-flash-lite @ https://api.quicksilverpro.io/v1
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

from qoresence.a2a.types import SceneProposal
from qoresence.agents.llm_client import DEFAULT_BASE_URL, _resolve_api_key

log = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.5-flash-lite"


class GeminiSceneAgent:
    """Sparse scene proposals for A2A (soft-only by default)."""

    def __init__(
        self,
        *,
        live: bool | None = None,
        model: str = GEMINI_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
        api_key_file: str | None = None,
    ) -> None:
        env_live = os.environ.get("QORESENCE_A2A_GEMINI", "0").strip() in {"1", "true", "yes"}
        self.live = env_live if live is None else bool(live)
        self.model = model or os.environ.get("QORESENCE_A2A_GEMINI_MODEL", GEMINI_MODEL)
        self.base_url = base_url.rstrip("/")
        self._api_key = _resolve_api_key(
            api_key or os.environ.get("QUICKSILVER_API_KEY"),
            api_key_file or os.environ.get("QUICKSILVER_API_KEY_FILE"),
        )
        if self.live and not self._api_key:
            log.warning("A2A Gemini live but no API key — using stub")
            self.live = False

    def propose_scene(
        self,
        *,
        situation: dict[str, Any] | None = None,
        coupling: float | None = None,
        drive_phase: str | None = None,
        frame_seq: int | None = None,
        jpeg_bytes: bytes | None = None,
    ) -> SceneProposal:
        if not self.live:
            return self._stub(situation, coupling, drive_phase, frame_seq)
        try:
            return self._live(situation, coupling, drive_phase, frame_seq, jpeg_bytes)
        except Exception as e:
            log.warning("Gemini scene live failed, stub: %s", e)
            return self._stub(situation, coupling, drive_phase, frame_seq)

    def _stub(
        self,
        situation: dict[str, Any] | None,
        coupling: float | None,
        drive_phase: str | None,
        frame_seq: int | None,
    ) -> SceneProposal:
        sit = situation or {}
        tags = []
        if sit.get("field_position"):
            tags.append("field")
        if drive_phase in ("pressure", "armed", "open"):
            tags.append(drive_phase)
        if coupling and coupling >= 0.45:
            tags.append("input_heat")
        summary = "live football pressure window" if tags else "quiet game state"
        if drive_phase:
            summary = f"{drive_phase} drive — {summary}"
        tension = min(1.0, 0.35 + (coupling or 0) * 0.5 + (0.2 if drive_phase == "armed" else 0))
        return SceneProposal(
            summary=summary[:200],
            tension=tension,
            tags=tags,
            soft_only=True,
            frame_seq=frame_seq,
            coupling=coupling,
            drive_phase=drive_phase,
            model="stub-gemini",
        )

    def _live(
        self,
        situation: dict[str, Any] | None,
        coupling: float | None,
        drive_phase: str | None,
        frame_seq: int | None,
        jpeg_bytes: bytes | None,
    ) -> SceneProposal:
        import requests

        sit = situation or {}
        prompt = (
            "You are a sports scene agent for a local observation system. "
            "Describe the clutch *feel* in one short sentence. "
            "Do NOT invent or state numeric scores, quarters as digits for the board, or down numbers. "
            "Use soft language only (pressure, red zone energy, late game heat). "
            f"Local context JSON (may be partial): {json.dumps({k: sit.get(k) for k in ('game_state','field_position','game_title') if sit.get(k)}, separators=(',',':'))[:400]}. "
            f"drive_phase={drive_phase} coupling={coupling}. "
            "Reply JSON: {\"summary\":\"...\",\"tension\":0.0-1.0,\"tags\":[\"...\"]}"
        )
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if jpeg_bytes:
            b64 = base64.b64encode(jpeg_bytes).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                }
            )
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 180,
            "temperature": 0.4,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"
        r = requests.post(url, headers=headers, json=body, timeout=12)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        raw = r.json()["choices"][0]["message"]["content"]
        summary, tension, tags = self._parse_jsonish(raw)
        return SceneProposal(
            summary=summary[:200],
            tension=tension,
            tags=tags,
            soft_only=True,
            frame_seq=frame_seq,
            coupling=coupling,
            drive_phase=drive_phase,
            model=self.model,
        )

    @staticmethod
    def _parse_jsonish(raw: str) -> tuple[str, float, list[str]]:
        text = (raw or "").strip()
        try:
            # strip markdown fences
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
            return (
                str(data.get("summary") or "scene pressure")[:200],
                float(data.get("tension") or 0.5),
                list(data.get("tags") or [])[:8],
            )
        except Exception:
            return text[:200] or "scene pressure", 0.5, []
