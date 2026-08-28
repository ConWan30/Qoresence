"""
Qoresence Visual Lobe

VLM integration for game-state classification and cross-modal verification.

Cloud path: Quicksilver Pro Gemini vision (default gemini-3.5-flash-lite).
That is the confirm-path referee: board + scene. LocalVLM only when
prefer_local=True or no Quicksilver key is present.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import cv2
import numpy as np
import requests

from qoresence.core import (
    RetinaEventBus,
    SourceLobe,
    VisualConfig,
    clock_ns,
)
from qoresence.vision.visual_context import (
    VisualContext,
)

log = logging.getLogger(__name__)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# DATA STRUCTURES
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# VisualContext is defined canonically in qoresence.vision.visual_context.
# It is re-exported here for backward compatibility.


@dataclass
class CrossModalVerdict:
    """Cross-modal verification result."""

    verdict: str  # "confirmed" | "inconclusive" | "contradicted"
    confidence: float
    reasoning: str
    modalities_checked: list[str]


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# VLM CLIENT
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class VLMClient:
    """Cloud VLM via Quicksilver Pro (or any OpenAI-compatible vision endpoint)."""

    def __init__(self, config: VisualConfig):
        self.config = config
        self.endpoint = config.model_endpoint.rstrip("/")
        self.model_name = config.model_name
        self.api_key = config.api_key
        # Resolve Quicksilver key if not set on config
        if not self.api_key:
            try:
                import pathlib

                from qoresence.agents.llm_client import _resolve_api_key

                key_file = None
                for p in (
                    ".secrets/quicksilver_clutchbot.key",
                    ".secrets/quicksilver_vlm.key",
                ):
                    if pathlib.Path(p).exists():
                        key_file = p
                        break
                self.api_key = _resolve_api_key(None, key_file)
            except Exception:
                pass
        self.max_dim = config.max_frame_dim
        self._session = requests.Session()

        # Headers
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Qoresence-VisualGemini/1.0",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        self._session.headers.update(headers)

    def analyze_frame_raw(
        self,
        frame: np.ndarray,
        prompt: str,
        timeout: float = 30.0,
        max_tokens: int = 300,
        **kwargs: object,
    ) -> str | None:
        """Send frame to VLM and return the raw response content.

        Extra kwargs (e.g. game_profile from VisionStack) are ignored by this
        transport — they only inform the prompt the caller already built.
        """
        try:
            # Resize frame
            h, w = frame.shape[:2]
            if max(h, w) > self.max_dim:
                scale = self.max_dim / max(h, w)
                new_w, new_h = int(w * scale), int(h * scale)
                frame = cv2.resize(frame, (new_w, new_h))

            # Encode to base64
            _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            b64 = base64.b64encode(buffer).decode("utf-8")

            # Build request (OpenAI-compatible format)
            payload = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                            },
                        ],
                    }
                ],
                "max_tokens": max_tokens,
                "temperature": 0.1,
            }

            response = self._session.post(
                f"{self.endpoint}/chat/completions",
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()

            return data.get("choices", [{}])[0].get("message", {}).get("content", "")

        except Exception as e:
            log.warning(f"VLM request failed: {e}")
            return None

    def analyze_frame(
        self, frame: np.ndarray, prompt: str, game_profile=None
    ) -> VisualContext | None:
        """Send frame to VLM for analysis and parse into VisualContext."""
        start = time.perf_counter()

        content = self.analyze_frame_raw(frame, prompt)
        if content is None:
            return None

        latency_ms = (time.perf_counter() - start) * 1000
        return self._parse_response(content, latency_ms)

    def _parse_response(self, content: str, latency_ms: float) -> VisualContext:
        """Parse VLM response into the canonical VisualContext."""
        details = {"raw_response": content}

        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end > start:
            try:
                parsed = json.loads(content[start : end + 1])
                if isinstance(parsed, dict):
                    ctx = VisualContext.from_dict(parsed)
                    ctx.details = {**details, **(ctx.details or {})}
                    ctx.raw_response = content[:500]
                    ctx.model = self.model_name
                    ctx.latency_ms = latency_ms
                    return ctx
            except json.JSONDecodeError:
                pass

        # Prefer explicit GAME_STATE / CONFIDENCE in the response
        state_match = re.search(r"GAME_STATE:\s*(\w+)", content, re.IGNORECASE)
        conf_match = re.search(r"CONFIDENCE:\s*([0-9]*\.?[0-9]+)", content, re.IGNORECASE)

        if state_match:
            game_state = state_match.group(1).lower()
            if game_state not in {"football", "shooter", "menu", "unknown"}:
                game_state = "unknown"
            confidence = float(conf_match.group(1)) if conf_match else 0.7
        else:
            # No structured answer: detect negation first, then topic keywords
            content_lower = content.lower()
            negation = any(
                phrase in content_lower
                for phrase in [
                    "does not show",
                    "is not",
                    "no ",
                    "not a",
                    "not show",
                    "not visible",
                    "unable to",
                    "can't",
                    "cannot",
                    "refuse",
                    "not able",
                    "i'm not able",
                ]
            )
            if negation:
                game_state = "unknown"
                confidence = 0.3
            elif any(
                kw in content_lower
                for kw in [
                    "football",
                    "ncaa",
                    "college football",
                    "touchdown",
                    "quarterback",
                    "field goal",
                    "yard line",
                ]
            ):
                game_state = "football"
                confidence = 0.8
            elif any(
                kw in content_lower
                for kw in [
                    "call of duty",
                    "warzone",
                    "multiplayer",
                    "shooter",
                    "fps",
                    "kill feed",
                    "operator",
                    "loadout",
                ]
            ):
                game_state = "shooter"
                confidence = 0.8
            elif any(
                kw in content_lower
                for kw in ["menu", "main menu", "settings", "lobby", "pause screen"]
            ):
                game_state = "menu"
                confidence = 0.6
            else:
                game_state = "unknown"
                confidence = 0.5

        ctx = VisualContext.from_dict(
            {
                "game_state": game_state,
                "confidence": confidence,
            }
        )
        ctx.details = details
        ctx.raw_response = content[:500]
        ctx.model = self.model_name
        ctx.latency_ms = latency_ms
        return ctx

    def cross_modal_check(
        self, frame: np.ndarray, other_modalities: dict
    ) -> CrossModalVerdict | None:
        """Cross-modal verification against other lobe data."""
        start = time.perf_counter()

        try:
            # Build prompt with other modality context
            modality_summary = "\n".join([f"- {k}: {v}" for k, v in other_modalities.items()])

            prompt = f"""You are verifying consistency between visual observation and other sensor data.
Other modalities:
{modality_summary}

Does the visual content match what these sensors indicate? Answer with:
VERDICT: confirmed|inconclusive|contradicted
CONFIDENCE: 0.0-1.0
REASONING: brief explanation"""

            _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            b64 = base64.b64encode(buffer).decode("utf-8")

            payload = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                            },
                        ],
                    }
                ],
                "max_tokens": 200,
                "temperature": 0.1,
            }

            response = self._session.post(
                f"{self.endpoint}/chat/completions",
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            latency_ms = (time.perf_counter() - start) * 1000
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            return self._parse_cross_modal(content, latency_ms, other_modalities)

        except Exception as e:
            log.warning(f"Cross-modal VLM request failed: {e}")
            return None

    def _parse_cross_modal(
        self, content: str, latency_ms: float, other_modalities: dict | None = None
    ) -> CrossModalVerdict:
        """Parse cross-modal response."""
        verdict = "inconclusive"
        confidence = 0.5
        reasoning = content

        content_lower = content.lower()
        if "verdict: confirmed" in content_lower:
            verdict = "confirmed"
            confidence = 0.8
        elif "verdict: contradicted" in content_lower:
            verdict = "contradicted"
            confidence = 0.8

        return CrossModalVerdict(
            verdict=verdict,
            confidence=confidence,
            reasoning=reasoning,
            modalities_checked=list(other_modalities.keys()) if other_modalities else [],
        )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# VISUAL RUNTIME
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class VisualRuntime:
    """
    Visual lobe using VLM for game-state classification and cross-modal verification.

    - Samples frames at configurable rate
    - Classifies game state (football/shooter/menu/unknown)
    - Cross-modal verification against controller/outcome/screen data
    - Emits visual_context and cross_modal_verdict events
    """

    def __init__(
        self,
        config: VisualConfig,
        bus: RetinaEventBus,
        session_head_ns: int,
        frame_provider: Callable[[], np.ndarray | None] | None = None,
        modality_provider: Callable[[], dict] | None = None,
    ):
        self.config = config
        self.bus = bus
        self.session_head_ns = session_head_ns

        # Optional providers
        self._frame_provider = frame_provider
        self._modality_provider = modality_provider

        # Gemini is the vision/confirm client. Local ONNX only if asked, or if
        # there is no Quicksilver key (offline play still has to start).
        self._client_kind = "cloud:gemini"
        _prefer = bool(getattr(config, "prefer_local", False))
        _local_path = getattr(config, "local_model_path", None)
        _fallback = bool(getattr(config, "local_fallback", True))
        _cloud = VLMClient(config)
        _has_gemini = bool(getattr(_cloud, "api_key", None))
        if _prefer or not _has_gemini:
            try:
                from qoresence.vision.local_vlm import LocalVLMClient as _LocalVLM

                _local = _LocalVLM(
                    model_path=_local_path,
                    game_profile=getattr(config, "game_profile", None),
                )
                if _prefer or _local.is_available() or _fallback:
                    self._client = _local
                    self._client_kind = (
                        "local:onnx" if _local.is_available() else "local:heuristic"
                    )
                    why = "prefer_local" if _prefer else "no Quicksilver key"
                    log.info(
                        "VisualRuntime using %s (%s, path=%s)",
                        self._client_kind,
                        why,
                        _local_path or "models/qoresence-vlm-distilled.onnx",
                    )
                else:
                    self._client = _cloud
                    self._client_kind = "cloud:gemini"
            except Exception as e:
                log.warning("LocalVLM init failed (%s), using Gemini if keyed", e)
                self._client = _cloud
                self._client_kind = "cloud:gemini"
        else:
            self._client = _cloud
            self._client_kind = "cloud:gemini"
            log.info(
                "VisualRuntime using Gemini confirm (%s)",
                getattr(config, "model_name", "gemini-3.5-flash-lite"),
            )

        # Prompts
        self._classify_prompt = self._build_classify_prompt()
        self._cross_modal_prompt = self._build_cross_modal_prompt()

        # State
        self._running = False
        self._thread: threading.Thread | None = None
        self._frames_analyzed = 0
        self._start_time = 0.0
        self._last_context: VisualContext | None = None
        self._last_verdict: CrossModalVerdict | None = None

        # Presence callback (for fusion engine)
        self._presence_callback: callable | None = None

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # PUBLIC API
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def start(self) -> bool:
        """Start analysis thread."""
        if self._running:
            log.warning("VisualRuntime already running")
            return True

        if self._frame_provider is None:
            log.warning("No frame provider set - visual lobe will not analyze frames")

        _register_runtime(self)
        self._running = True
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._run_loop, name="qoresence-visual", daemon=True)
        self._thread.start()

        log.info(
            f"Visual lobe started: model={self.config.model_name}, sample_rate={self.config.frame_sample_rate}"
        )
        return True

    def stop(self) -> None:
        """Stop analysis thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        _unregister_runtime(self)
        log.info("Visual lobe stopped")

    def is_running(self) -> bool:
        return self._running

    def set_presence_callback(self, callback: callable) -> None:
        """Set callback for presence status updates (for fusion engine)."""
        self._presence_callback = callback

    def get_last_state(self) -> dict:
        """Get last visual state for cross-modal verification."""
        return {
            "game_state": self._last_context.game_state.value if self._last_context else "unknown",
            "confidence": self._last_context.confidence if self._last_context else 0.0,
            "last_verdict": self._last_verdict.verdict if self._last_verdict else "inconclusive",
        }

    def set_frame_provider(self, provider: Callable[[], np.ndarray | None]) -> None:
        """Set frame provider (e.g., from streamer or screen lobe)."""
        self._frame_provider = provider

    def set_modality_provider(self, provider: Callable[[], dict]) -> None:
        """Set provider for other modality data (for cross-modal check)."""
        self._modality_provider = provider

    def get_last_context(self) -> VisualContext | None:
        return self._last_context

    def get_last_verdict(self) -> CrossModalVerdict | None:
        return self._last_verdict

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # MAIN LOOP
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _run_loop(self) -> None:
        """Main analysis loop."""
        frame_count = 0

        # Emit session_start
        self._emit_session_start()

        while self._running:
            loop_start = time.time()

            # Get frame
            frame = self._get_frame()
            if frame is not None:
                frame_count += 1

                # Analyze every N frames
                if frame_count % self.config.frame_sample_rate == 0:
                    self._analyze_frame(frame)

            # Pace (roughly 30fps max for frame fetching)
            elapsed = time.time() - loop_start
            sleep_time = max(0.033 - elapsed, 0.001)
            time.sleep(sleep_time)

        # Session end
        self._emit_session_end()

    def _get_frame(self) -> np.ndarray | None:
        """Get frame from provider."""
        if self._frame_provider:
            try:
                return self._frame_provider()
            except Exception as e:
                log.warning(f"Frame provider error: {e}")
        return None

    def _analyze_frame(self, frame: np.ndarray) -> None:
        """Classify, then always merge Gemini scoreboard lock/ticket on football."""
        hub_seq: int | None = None
        hub_clock = clock_ns()
        try:
            from qoresence.monitor.frame_hub import get_latest_stamp

            st = get_latest_stamp()
            if st.get("has_frame"):
                hub_seq = int(st.get("seq") or 0) or None
                hub_clock = int(st.get("clock_ns") or hub_clock)
        except Exception:
            pass

        # Keep local vision processing bounded; the local ONNX classifier runs at
        # 224x224 anyway, and downstream scoreboard extractors should not have to
        # allocate on full-res HDMI frames.
        h, w = frame.shape[:2]
        if max(h, w) > self.config.max_frame_dim:
            scale = self.config.max_frame_dim / max(h, w)
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

        # 1. Game state classification
        context = self._client.analyze_frame(
            frame,
            self._classify_prompt,
            game_profile=self.config.game_profile or self.config.game_category,
        )
        context = self._merge_scoreboard(frame, context)
        if context is not None:
            self._maybe_mint_picture_hid(context, frame_seq=hub_seq, clock_ns=hub_clock)
        if context and (
            context.confidence >= self.config.min_confidence
            or context.score_vlm_locked
            or context.home_score is not None
            or context.visible_control
        ):
            self._last_context = context
            self._emit_visual_context(context)

        # 2. Cross-modal verification (if modality provider available)
        if self._modality_provider and self._last_context:
            other_modalities = self._modality_provider()
            if other_modalities:
                verdict = self._client.cross_modal_check(frame, other_modalities)
                if verdict:
                    self._last_verdict = verdict
                    self._emit_cross_modal_verdict(verdict)

        self._frames_analyzed += 1

    def _merge_scoreboard(self, frame: np.ndarray, context: VisualContext | None) -> VisualContext | None:
        """Always run the extractor so Gemini get_last() becomes a lock + ticket.

        Cloud VisualRuntime used to skip this; LocalVLM was the only caller.
        A2A still schedules the referee, but without extract() scores never land.
        """
        profile = str(self.config.game_profile or self.config.game_category or "")
        football = "football" in profile.lower() or "ncaa" in profile.lower() or "madden" in profile.lower() or "cfb" in profile.lower()

        # Map title/profile to canonical profile_id
        title_lower = str(getattr(context, "game_title", "") or "").lower() if context else ""
        config_lower = profile.lower()

        if "college" in title_lower or "college" in config_lower or "ncaa" in title_lower or "ncaa" in config_lower or "cfb" in title_lower or "cfb" in config_lower:
            profile = "cfb_27"
        elif "madden" in title_lower or "madden" in config_lower:
            profile = "madden_27"

        if context is None:
            if not football:
                return None
            from qoresence.vision.visual_context import GameCategory, GameState

            context = VisualContext(
                game_category=GameCategory.FOOTBALL,
                game_state=GameState.GAMEPLAY,
                game_profile=profile,
                confidence=0.0,
            )
        else:
            # Update context.game_profile based on merged title + config
            context.game_profile = profile
        try:
            cat = getattr(context.game_category, "value", context.game_category)
            if not football and str(cat) != "football":
                return context
            if str(cat) != "football":
                from qoresence.vision.visual_context import GameCategory

                context.game_category = GameCategory.FOOTBALL
            from qoresence.vision.scoreboard_extractor import extract_football_scoreboard

            return extract_football_scoreboard(frame, context)
        except Exception as e:
            log.debug("scoreboard merge skipped: %s", e)
            return context

    def _maybe_mint_picture_hid(
        self,
        context: VisualContext,
        *,
        frame_seq: int | None,
        clock_ns: int,
    ) -> None:
        """Mint PictureHidTicket on the visual worker (never grab thread)."""
        try:
            from qoresence.vision.picture_hid_ticket import try_mint_picture_hid_from_context

            model = str(getattr(self.config, "model_name", "") or "gemini-3.5-flash-lite")
            source = "quicksilver" if "quicksilver" in model.lower() else "gemini"
            try_mint_picture_hid_from_context(
                context,
                frame_seq=frame_seq,
                clock_ns=clock_ns,
                source=source,
                model=model,
            )
        except Exception as e:
            log.debug("picture hid mint skipped: %s", e)

    # Prompts
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _build_classify_prompt(self) -> str:
        """Build classification prompt based on game category."""
        category = self.config.game_category
        if category == "football":
            from qoresence.vision.visual_context import build_football_prompt

            return build_football_prompt()
        elif category == "shooter":
            return """Look at this image. If it shows Call of Duty (Warzone/Multiplayer) gameplay (weapon, mini-map, kill feed, operator), answer shooter. If it shows a menu/lobby, answer menu. Otherwise answer unknown.

Respond ONLY with:
GAME_STATE: shooter|menu|unknown
CONFIDENCE: 0.0-1.0

Do not add any explanation."""
        else:
            return """Identify the game type in this image.
Options: football (NCAA/sports), shooter (FPS/Call of Duty), menu, unknown.

Respond ONLY with:
GAME_STATE: football|shooter|menu|unknown
CONFIDENCE: 0.0-1.0

Do not add any explanation."""

    def _build_cross_modal_prompt(self) -> str:
        return """Verify visual consistency with other sensor data."""

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # EVENT EMISSION
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _emit_session_start(self) -> None:
        self.bus.emit_raw(
            source_lobe=SourceLobe.VISUAL,
            event_type="session_start",
            payload={
                "model_endpoint": self.config.model_endpoint,
                "model_name": self.config.model_name,
                "frame_sample_rate": self.config.frame_sample_rate,
                "max_frame_dim": self.config.max_frame_dim,
                "min_confidence": self.config.min_confidence,
                "game_category": self.config.game_category,
            },
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )

    def _emit_visual_context(self, context: VisualContext) -> None:
        """Emit the canonical visual_context payload."""
        self.bus.emit_raw(
            source_lobe=SourceLobe.VISUAL,
            event_type="visual_context",
            payload=context.to_dict(),
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )

        # Call presence callback for fusion engine
        if self._presence_callback:
            try:
                self._presence_callback(
                    {
                        "lobe": "visual",
                        "game_state": context.game_state.value,
                        "confidence": context.confidence,
                    }
                )
            except Exception:
                pass

    def _emit_cross_modal_verdict(self, verdict: CrossModalVerdict) -> None:
        self.bus.emit_raw(
            source_lobe=SourceLobe.VISUAL,
            event_type="cross_modal_verdict",
            payload={
                "verdict": verdict.verdict,
                "confidence": verdict.confidence,
                "reasoning": verdict.reasoning,
                "modalities_checked": verdict.modalities_checked,
            },
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )

    def _emit_session_end(self) -> None:
        elapsed = max(time.time() - self._start_time, 1e-6)
        self.bus.emit_raw(
            source_lobe=SourceLobe.VISUAL,
            event_type="session_end",
            payload={
                "frames_analyzed": self._frames_analyzed,
                "elapsed_s": round(elapsed, 2),
            },
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# MOCK VLM CLIENT (for testing without API)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class MockVLMClient:
    """Mock VLM client for testing without real API."""

    def __init__(self, config: VisualConfig):
        self.config = config

    def analyze_frame(
        self, frame: np.ndarray, prompt: str, game_profile=None
    ) -> VisualContext | None:
        # Simple heuristic based on frame content
        h, w = frame.shape[:2]
        mean_brightness = np.mean(frame) / 255.0

        # Heuristic: green field -> football, dark with UI -> shooter
        green_pixels = np.sum((frame[:, :, 1] > frame[:, :, 0]) & (frame[:, :, 1] > frame[:, :, 2]))
        green_ratio = green_pixels / (h * w)

        if green_ratio > 0.15:
            game_state = "football"
            confidence = 0.85
        elif mean_brightness < 0.3:
            game_state = "shooter"
            confidence = 0.8
        else:
            game_state = "unknown"
            confidence = 0.3

        ctx = VisualContext.from_dict(
            {
                "game_state": game_state,
                "confidence": confidence,
            }
        )
        ctx.details = {"mock": True, "green_ratio": green_ratio, "brightness": mean_brightness}
        ctx.model = "mock"
        ctx.latency_ms = 10.0
        return ctx

    def cross_modal_check(
        self, frame: np.ndarray, other_modalities: dict
    ) -> CrossModalVerdict | None:
        # Simple mock: confirmed if outcome and controller both present
        has_outcome = "outcome" in str(other_modalities).lower()
        has_controller = "controller" in str(other_modalities).lower()

        if has_outcome and has_controller:
            return CrossModalVerdict(
                verdict="confirmed",
                confidence=0.9,
                reasoning="Mock: outcome and controller data present",
                modalities_checked=list(other_modalities.keys()),
            )
        return CrossModalVerdict(
            verdict="inconclusive",
            confidence=0.5,
            reasoning="Mock: insufficient modality data",
            modalities_checked=list(other_modalities.keys()),
        )


# ────────────────────────────────────────────────────────────────────────────
# MODULE REGISTRY (same pattern as controller runtime)
# ────────────────────────────────────────────────────────────────────────────

_active: VisualRuntime | None = None
_active_lock = threading.Lock()


def _register_runtime(runtime: VisualRuntime) -> None:
    global _active
    with _active_lock:
        _active = runtime


def _unregister_runtime(runtime: VisualRuntime) -> None:
    global _active
    with _active_lock:
        if _active is runtime:
            _active = None


def get_visual_runtime() -> VisualRuntime | None:
    """Process-local visual lobe (None if not started)."""
    return _active


def get_last_visual_context() -> VisualContext | None:
    """Get last VisualContext from active visual runtime.

    Convenience wrapper for observation wire and other consumers.
    Returns None if visual lobe is not started or has no context yet.
    """
    runtime = get_visual_runtime()
    if runtime is None:
        return None
    return runtime.get_last_context()
