"""Qwen3.6-VL local adapter scaffold (Trio P5: frozen-foundation + adapter).

This module provides a scaffold for running a local Qwen3.6-VL (or similar
transformer-based VLM) as the visual reasoning tier, with optional LoRA
adapter loading per game profile.

Architecture (Trio Principle 5):
    Frozen VLM foundation (Qwen3.6-VL) → LoRA adapter per game profile
    → distilled ONNX export for <100ms inference path

Current state: SCAFFOLD ONLY. The actual model loading and inference
requires `transformers`, `torch`, and a GPU with >=8GB VRAM. The
scaffold provides:
  1. A QwenVLMAdapter class with a clear interface
  2. LoRA adapter path resolution per game profile
  3. A graceful fallback to LocalVLMClient when the model is unavailable
  4. A prompt template system for game-profile-specific visual queries

When the model is available (QORESENCE_LOCAL_VLM=qwen), the adapter:
  - Loads the frozen Qwen3.6-VL base model
  - Attaches a LoRA adapter from models/adapters/<profile_id>.lora/
  - Runs visual question answering on each frame
  - Returns a VisualContext with structured fields

When unavailable, it falls back to LocalVLMClient (heuristic/ONNX).
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from qoresence.vision.local_vlm import LocalVLMClient
from qoresence.vision.visual_context import VisualContext

log = logging.getLogger(__name__)

# Default model paths
_MODELS_DIR = Path("models")
_ADAPTERS_DIR = _MODELS_DIR / "adapters"
_QWEN_BASE_MODEL = os.environ.get(
    "QORESENCE_QWEN_MODEL", "Qwen/Qwen3.6-VL-7B-Instruct"
)

# Prompt templates per game category
_PROMPT_TEMPLATES: dict[str, str] = {
    "football": (
        "You are analyzing a college football game screenshot. "
        "Extract the following fields from the scoreboard overlay: "
        "home_score (integer), away_score (integer), quarter (1-5), "
        "down (1-4), yards_to_go (integer), possession (home/away), "
        "field_position (e.g. 'OPP 25'), game_clock (MM:SS format). "
        "Also identify the game_state (menu/gameplay/replay/highlight). "
        "Respond as JSON. If a field is not visible, use null."
    ),
    "shooter": (
        "You are analyzing a first-person shooter game screenshot. "
        "Extract: kills (integer), deaths (integer), score (integer), "
        "health (0-100), ammo (integer), game_state (menu/gameplay/death). "
        "Respond as JSON. If a field is not visible, use null."
    ),
    "default": (
        "Analyze this game screenshot. Identify the game_state "
        "(menu/gameplay/replay) and any visible HUD elements. "
        "Respond as JSON."
    ),
}


def get_prompt_for_category(category: str | None) -> str:
    """Get the VQA prompt template for a game category."""
    if not category:
        return _PROMPT_TEMPLATES["default"]
    return _PROMPT_TEMPLATES.get(category.lower(), _PROMPT_TEMPLATES["default"])


def get_adapter_path(profile_id: str | None) -> Path | None:
    """Resolve the LoRA adapter path for a game profile.

    Returns None if no adapter is found.
    """
    if not profile_id:
        return None
    # Try several naming conventions
    candidates = [
        _ADAPTERS_DIR / f"{profile_id}.lora",
        _ADAPTERS_DIR / profile_id / "adapter",
        _ADAPTERS_DIR / f"{profile_id}_adapter",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


class QwenVLMAdapter:
    """Local Qwen3.6-VL adapter with optional LoRA per game profile.

    This is a scaffold that gracefully falls back to LocalVLMClient
    when the model is not available. When QORESENCE_LOCAL_VLM=qwen
    and the model is loadable, it uses the transformer-based VLM path.

    The adapter pattern follows Trio P5:
    - Frozen foundation model (Qwen3.6-VL base)
    - Per-profile LoRA adapter (lightweight, <100MB)
    - Distilled ONNX export for production inference (<100ms)
    """

    def __init__(
        self,
        *,
        profile_id: str | None = None,
        game_category: str | None = None,
        model_name: str | None = None,
        device: str = "auto",
        fallback: LocalVLMClient | None = None,
    ) -> None:
        self.profile_id = profile_id
        self.game_category = game_category
        self.model_name = model_name or _QWEN_BASE_MODEL
        self.device = device
        self._fallback = fallback or LocalVLMClient()
        self._model = None
        self._processor = None
        self._adapter_path = get_adapter_path(profile_id)
        self._available = False
        self._mode = "fallback"
        self._stats: dict[str, Any] = {
            "calls": 0,
            "avg_ms": 0.0,
            "model": "fallback",
            "adapter_loaded": False,
        }

        # Try to load the model
        env_enabled = os.environ.get("QORESENCE_LOCAL_VLM", "").lower() in {"qwen", "1", "true"}
        if env_enabled:
            self._try_load()

    def _try_load(self) -> None:
        """Attempt to load the Qwen3.6-VL model and LoRA adapter."""
        try:
            import torch  # type: ignore
            from transformers import AutoModelForVision2Seq, AutoProcessor  # type: ignore

            # Resolve device
            if self.device == "auto":
                self.device = "cuda" if torch.cuda.is_available() else "cpu"

            log.info("Loading Qwen3.6-VL: %s on %s", self.model_name, self.device)
            self._processor = AutoProcessor.from_pretrained(self.model_name)
            self._model = AutoModelForVision2Seq.from_pretrained(
                self.model_name,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                device_map=self.device,
            )

            # Load LoRA adapter if available
            if self._adapter_path and self._adapter_path.exists():
                try:
                    from peft import PeftModel  # type: ignore

                    self._model = PeftModel.from_pretrained(
                        self._model, str(self._adapter_path)
                    )
                    self._stats["adapter_loaded"] = True
                    log.info("LoRA adapter loaded: %s", self._adapter_path)
                except ImportError:
                    log.warning("peft not installed — LoRA adapter skipped")
                except Exception as e:
                    log.warning("LoRA adapter load failed: %s", e)

            self._available = True
            self._mode = "qwen"
            self._stats["model"] = self.model_name
            log.info("Qwen3.6-VL loaded successfully (mode=qwen)")
        except ImportError:
            log.info("Qwen3.6-VL dependencies not installed — using fallback")
        except Exception as e:
            log.warning("Qwen3.6-VL load failed: %s — using fallback", e)

    @property
    def available(self) -> bool:
        return self._available

    @property
    def mode(self) -> str:
        return self._mode

    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    def analyze_frame(
        self,
        frame: Any,
        *,
        frame_seq: int | None = None,
    ) -> VisualContext:
        """Analyze a frame and return a VisualContext.

        If the Qwen model is available, runs VQA with the game-profile
        prompt template. Otherwise, delegates to LocalVLMClient.
        """
        t0 = time.monotonic()
        self._stats["calls"] += 1

        if self._available and self._model is not None:
            try:
                vc = self._qwen_analyze(frame, frame_seq)
                elapsed = (time.monotonic() - t0) * 1000
                self._stats["avg_ms"] = (
                    self._stats["avg_ms"] * (self._stats["calls"] - 1) + elapsed
                ) / self._stats["calls"]
                return vc
            except Exception as e:
                log.warning("Qwen analysis failed, falling back: %s", e)

        # Fallback to LocalVLMClient (signature: analyze_frame(frame, prompt, game_profile))
        vc = self._fallback.analyze_frame(frame, game_profile=self.profile_id)
        if vc is None:
            vc = VisualContext(game_state="unknown", confidence=0.0, model="fallback")
        elapsed = (time.monotonic() - t0) * 1000
        self._stats["avg_ms"] = (
            self._stats["avg_ms"] * (self._stats["calls"] - 1) + elapsed
        ) / self._stats["calls"]
        return vc

    def _qwen_analyze(self, frame: Any, frame_seq: int | None) -> VisualContext:
        """Run Qwen3.6-VL visual question answering on a frame."""
        import json

        import torch  # type: ignore
        from PIL import Image  # type: ignore

        # Convert numpy frame to PIL Image
        if hasattr(frame, "shape"):
            # numpy array (BGR or RGB)
            img = Image.fromarray(frame[:, :, ::-1] if frame.shape[-1] == 3 else frame)
        elif isinstance(frame, (bytes, bytearray)):
            import io

            img = Image.open(io.BytesIO(frame))
        else:
            img = frame  # assume PIL Image

        prompt = get_prompt_for_category(self.game_category)

        # Build chat messages
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": img},
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        text = self._processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self._processor(
            text=[text], images=[img], return_tensors="pt", padding=True
        ).to(self.device)

        with torch.no_grad():
            output_ids = self._model.generate(
                **inputs,
                max_new_tokens=256,
                do_sample=False,
                temperature=1.0,
            )

        # Decode the response
        generated = output_ids[:, inputs["input_ids"].shape[1]:]
        response = self._processor.batch_decode(generated, skip_special_tokens=True)[0]

        # Parse JSON response into VisualContext
        return self._parse_qwen_response(response, frame_seq)

    def _parse_qwen_response(
        self, response: str, frame_seq: int | None
    ) -> VisualContext:
        """Parse Qwen VLM JSON response into a VisualContext."""
        import json

        try:
            # Strip markdown fences if present
            text = response.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
        except Exception:
            # If parsing fails, return a basic VisualContext
            return VisualContext(
                game_state="gameplay",
                confidence=0.3,
                model="qwen-vlm",
                raw_response=response[:200],
            )

        # Map JSON fields to VisualContext
        vc = VisualContext(
            game_state=str(data.get("game_state") or "gameplay").lower(),
            confidence=float(data.get("confidence") or 0.7),
            model="qwen-vlm",
            raw_response=response[:200],
        )

        # Football fields
        if self.game_category == "football":
            vc.home_score = data.get("home_score")
            vc.away_score = data.get("away_score")
            vc.quarter = data.get("quarter")
            vc.down = data.get("down")
            vc.yards_to_go = data.get("yards_to_go")
            vc.possession = data.get("possession")
            vc.field_position = data.get("field_position")
            # game_clock is a string like "8:32" — convert to seconds
            game_clock = data.get("game_clock")
            if game_clock and isinstance(game_clock, str) and ":" in game_clock:
                try:
                    parts = game_clock.split(":")
                    vc.clock_seconds = int(parts[0]) * 60 + int(parts[1])
                except (ValueError, IndexError):
                    pass

        # Shooter fields
        if self.game_category in ("shooter", "fps"):
            vc.kills = data.get("kills")
            vc.deaths = data.get("deaths")
            vc.score = data.get("score")
            vc.health = data.get("health")
            vc.ammo = data.get("ammo")

        return vc


def create_local_vlm(
    *,
    profile_id: str | None = None,
    game_category: str | None = None,
    prefer_qwen: bool | None = None,
) -> QwenVLMAdapter | LocalVLMClient:
    """Factory for creating the appropriate local VLM client.

    Args:
        profile_id: Game profile ID for LoRA adapter selection
        game_category: Game category for prompt template selection
        prefer_qwen: If True, return a QwenVLMAdapter (with internal fallback
            to LocalVLMClient when the model is not installed). If None, check env.

    Returns:
        QwenVLMAdapter if Qwen is preferred, else LocalVLMClient.
        The QwenVLMAdapter gracefully falls back to LocalVLMClient internally
        when the transformer model is not available.
    """
    if prefer_qwen is None:
        prefer_qwen = os.environ.get("QORESENCE_LOCAL_VLM", "").lower() in {"qwen", "1", "true"}

    if prefer_qwen:
        adapter = QwenVLMAdapter(
            profile_id=profile_id,
            game_category=game_category,
        )
        log.info(
            "Qwen VLM adapter created (mode=%s, available=%s)",
            adapter.mode, adapter.available,
        )
        return adapter

    return LocalVLMClient(game_profile=profile_id)
