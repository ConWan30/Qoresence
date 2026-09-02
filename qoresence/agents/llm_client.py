"""ClutchBot LLM client — Quicksilver Pro (OpenAI-compatible).

Dedicated API for ClutchBot via https://api.quicksilverpro.io/v1
Default model: glm-5.3-flash (Quicksilver Pro). Falls back to gpt-4o-mini.

No new deps — uses requests if available, stdlib http otherwise.
Key is resolved from ClutchBotConfig.llm_api_key or llm_api_key_file
(never committed; .gitignore covers .secrets/ and *.key).
"""

from __future__ import annotations

import json
import logging
import pathlib
import time
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    requests = None  # type: ignore
    HAS_REQUESTS = False

DEFAULT_BASE_URL = "https://api.quicksilverpro.io/v1"
DEFAULT_MODEL = "glm-5.3-flash"
# Confirm-path VLM: Quicksilver vision slug (JPEG crop → JSON).
# Operator pin 2026-09-01: qwen3.7-flash. glm-5.3-flash chat is text-only;
# JPEG crop on the chat slug is 400 model_not_found. Not Gemini.
DEFAULT_VISION_MODEL = "qwen3.7-flash"
FALLBACK_MODEL = "gpt-4o-mini"
CLUTCHBOT_KEY_FILE = ".secrets/quicksilver_clutchbot.key"
# Already-documented optional vision key. Do not invent a new filename.
VLM_KEY_FILE = ".secrets/quicksilver_vlm.key"


def default_quicksilver_key_file() -> str | None:
    """Same key file ClutchBot / A2A DeepSeek use. Never invent a path that is missing."""
    p = pathlib.Path(CLUTCHBOT_KEY_FILE)
    return str(p) if p.exists() else None


def _resolve_api_key(api_key: str | None, api_key_file: str | None) -> str | None:
    if api_key and api_key.strip():
        return api_key.strip()
    if api_key_file:
        try:
            p = pathlib.Path(api_key_file)
            if p.exists():
                return p.read_text(encoding="utf-8").strip()
            log.warning(f"LLM api_key_file not found: {api_key_file}")
        except Exception as e:
            log.warning(f"LLM api_key_file read failed: {e}")
    # also try env vars as last resort (Quicksilver)
    import os

    for k in (
        "QUICKSILVER_API_KEY",
        "QUICKSILVERPRO_API_KEY",
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
    ):
        v = os.environ.get(k)
        if v and v.strip():
            return v.strip()
    return None


@dataclass
class LLMConfig:
    enabled: bool = False
    provider: str = "quicksilver"
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    api_key: str | None = None
    api_key_file: str | None = None
    fallback_model: str = FALLBACK_MODEL
    timeout_s: float = 6.0
    max_tokens: int = 256

    @classmethod
    def from_clutchbot(cls, cfg: Any) -> LLMConfig:
        return cls(
            enabled=bool(getattr(cfg, "llm_enabled", False)),
            provider=str(getattr(cfg, "llm_provider", "quicksilver") or "quicksilver"),
            model=str(getattr(cfg, "llm_model", DEFAULT_MODEL) or DEFAULT_MODEL),
            base_url=str(getattr(cfg, "llm_base_url", DEFAULT_BASE_URL) or DEFAULT_BASE_URL),
            api_key=getattr(cfg, "llm_api_key", None),
            api_key_file=getattr(cfg, "llm_api_key_file", None) or default_quicksilver_key_file(),
            fallback_model=str(
                getattr(cfg, "llm_fallback_model", FALLBACK_MODEL) or FALLBACK_MODEL
            ),
            timeout_s=float(getattr(cfg, "llm_timeout_s", 6.0) or 6.0),
            max_tokens=int(getattr(cfg, "llm_max_tokens", 256) or 256),
        )

    @classmethod
    def from_quicksilver_env(cls, *, enabled: bool = False) -> LLMConfig:
        """Match-observer path: ClutchBot chat slug on Quicksilver, ClutchBot key file."""
        import os

        model = os.environ.get("QORESENCE_MATCH_AGENT_MODEL") or os.environ.get(
            "QORESENCE_CLUTCHBOT_LLM_MODEL", DEFAULT_MODEL
        )
        base = os.environ.get("QORESENCE_CLUTCHBOT_LLM_BASE_URL", DEFAULT_BASE_URL)
        key_file = (
            os.environ.get("QORESENCE_CLUTCHBOT_LLM_API_KEY_FILE")
            or os.environ.get("QUICKSILVER_API_KEY_FILE")
            or default_quicksilver_key_file()
        )
        return cls(
            enabled=bool(enabled),
            provider="quicksilver",
            model=str(model or DEFAULT_MODEL),
            base_url=str(base or DEFAULT_BASE_URL),
            api_key=os.environ.get("QORESENCE_CLUTCHBOT_LLM_API_KEY") or None,
            api_key_file=key_file,
            timeout_s=8.0,
            max_tokens=180,
        )

    @classmethod
    def from_scoreboard_vlm(cls) -> LLMConfig:
        """Confirm-path VLM: same Quicksilver API + clutchbot key as ClutchBot.

        Model default is ``qwen3.7-flash`` (JPEG in / JSON out) on the same
        Quicksilver API + clutchbot key as ClutchBot. Not Gemini.
        ``quicksilver_vlm.key`` is a fallback only.
        """
        import os

        model = os.environ.get("QORESENCE_SCOREBOARD_VLM_MODEL") or DEFAULT_VISION_MODEL
        base = (
            os.environ.get("QORESENCE_SCOREBOARD_VLM_BASE_URL")
            or os.environ.get("QORESENCE_CLUTCHBOT_LLM_BASE_URL")
            or DEFAULT_BASE_URL
        )
        key_file = (
            os.environ.get("QORESENCE_SCOREBOARD_VLM_KEY_FILE")
            or os.environ.get("QORESENCE_CLUTCHBOT_LLM_API_KEY_FILE")
            or os.environ.get("QUICKSILVER_API_KEY_FILE")
            or default_quicksilver_key_file()
        )
        if not key_file:
            vlm_key = pathlib.Path(VLM_KEY_FILE)
            if vlm_key.exists():
                key_file = str(vlm_key)
        return cls(
            enabled=True,
            provider="quicksilver",
            model=str(model or DEFAULT_VISION_MODEL),
            base_url=str(base or DEFAULT_BASE_URL),
            api_key=(
                os.environ.get("QORESENCE_SCOREBOARD_VLM_API_KEY")
                or os.environ.get("QORESENCE_CLUTCHBOT_LLM_API_KEY")
                or None
            ),
            api_key_file=key_file,
            timeout_s=14.0,
            max_tokens=400,
        )


def _build_system_prompt(persona: str, game_title: str | None) -> str:
    persona = (persona or "neutral").strip()
    game = game_title or "NCAA Football 27"
    return (
        f"You are ClutchBot, persona={persona} for {game}. "
        "You narrate clutch moments for Twitch chat. "
        "Ground ONLY on the SituationState JSON provided. Never hallucinate score, quarter, down, or possession. "
        "Keep chat <140 chars, hype but not cringe, no hashtags. "
        "If situation is uncertain, say nothing. Never claim to be human."
    )


def _build_user_prompt(
    situation: dict[str, Any],
    event_type: str,
    event_payload: dict[str, Any] | None,
    base_message: str | None = None,
) -> str:
    # Truncate payload to avoid token bloat
    payload_str = ""
    if event_payload:
        try:
            payload_str = json.dumps(event_payload, separators=(",", ":"))[:1200]
        except Exception:
            payload_str = str(event_payload)[:800]
    sit_str = json.dumps(situation, separators=(",", ":"))[:2000]
    parts = [
        f"Situation: {sit_str}",
        f"Trigger event: {event_type}",
    ]
    if payload_str:
        parts.append(f"Event payload: {payload_str}")
    if base_message:
        parts.append(f"Template message (rewrite, keep meaning): {base_message}")
    parts.append("Respond with ONE chat line only. No quotes, no prefix.")
    return "\n".join(parts)


class QuicksilverLLMClient:
    """Thin OpenAI-compatible client for Quicksilver Pro."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._api_key = _resolve_api_key(config.api_key, config.api_key_file)
        self._session_ok = bool(config.enabled and self._api_key)

        if config.enabled and not self._api_key:
            log.warning(
                "ClutchBot LLM enabled but no API key resolved "
                "(set llm_api_key or llm_api_key_file or QUICKSILVER_API_KEY). LLM disabled."
            )
            self._session_ok = False

    def is_available(self) -> bool:
        return bool(self._session_ok and self._api_key)

    # -- low-level call ----------------------------------------------------

    def _post_chat(self, messages: list[dict[str, str]], model: str | None = None) -> str | None:
        if not self.is_available():
            return None
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        mdl = model or self.config.model
        body = {
            "model": mdl,
            "messages": messages,
            "max_tokens": self.config.max_tokens,
            "temperature": 0.7,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        start = time.time()
        try:
            if HAS_REQUESTS:
                resp = requests.post(url, headers=headers, json=body, timeout=self.config.timeout_s)  # type: ignore
                elapsed = time.time() - start
                if resp.status_code != 200:
                    log.warning(
                        f"Quicksilver LLM {mdl} HTTP {resp.status_code}: {resp.text[:400]} ({elapsed:.2f}s)"
                    )
                    # fallback once on 404/429 for model
                    if resp.status_code in (404, 429) and mdl != self.config.fallback_model:
                        log.info(f"LLM fallback to {self.config.fallback_model}")
                        return self._post_chat(messages, model=self.config.fallback_model)
                    return None
                data = resp.json()
            else:
                # stdlib fallback
                import http.client
                import urllib.parse

                parsed = urllib.parse.urlparse(url)
                conn_cls = (
                    http.client.HTTPSConnection
                    if parsed.scheme == "https"
                    else http.client.HTTPConnection
                )
                conn = conn_cls(
                    parsed.hostname or "", parsed.port or 443, timeout=self.config.timeout_s
                )
                body_s = json.dumps(body)
                conn.request(
                    "POST", parsed.path or "/v1/chat/completions", body=body_s, headers=headers
                )
                resp2 = conn.getresponse()
                raw = resp2.read().decode("utf-8", errors="replace")
                elapsed = time.time() - start
                if resp2.status != 200:
                    log.warning(
                        f"Quicksilver LLM {mdl} HTTP {resp2.status}: {raw[:400]} ({elapsed:.2f}s)"
                    )
                    if resp2.status in (404, 429) and mdl != self.config.fallback_model:
                        return self._post_chat(messages, model=self.config.fallback_model)
                    return None
                data = json.loads(raw)

            # OpenAI shape: choices[0].message.content
            try:
                content = data["choices"][0]["message"]["content"]
                if isinstance(content, str):
                    content = content.strip().strip('"').strip("'")
                    log.debug(f"LLM {mdl} ok {elapsed:.2f}s: {content[:120]}")
                    return content
            except Exception as e:
                log.warning(f"LLM parse failed: {e} data={str(data)[:500]}")
                return None
            return None
        except Exception as e:
            log.warning(f"Quicksilver LLM call failed ({mdl}): {e}")
            return None

    # -- high-level: enhance a ScoredMoment chat message -------------------

    def enhance_message(
        self,
        situation: dict[str, Any],
        event_type: str,
        event_payload: dict[str, Any] | None,
        persona: str = "neutral",
        base_message: str | None = None,
        system_prompt: str | None = None,
    ) -> str | None:
        """Rewrite/enhance a chat message via LLM. Returns None on failure (caller keeps template)."""
        if not self.is_available():
            return None
        game_title = situation.get("game_title") if isinstance(situation, dict) else None
        messages = [
            {
                "role": "system",
                "content": system_prompt
                or _build_system_prompt(
                    persona, game_title if isinstance(game_title, str) else None
                ),
            },
            {
                "role": "user",
                "content": _build_user_prompt(situation, event_type, event_payload, base_message),
            },
        ]
        out = self._post_chat(messages)
        if out and len(out) > 4 and len(out) < 300:
            return out
        return None

    def generate_chat(
        self,
        situation: dict[str, Any],
        event_type: str,
        event_payload: dict[str, Any] | None = None,
        persona: str = "neutral",
    ) -> str | None:
        return self.enhance_message(
            situation, event_type, event_payload, persona, base_message=None
        )
