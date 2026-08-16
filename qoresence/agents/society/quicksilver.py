"""Thin Quicksilver chat client — phrasing/reasoning only. No score truth."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path

from .config import AgentSocietyConfig

log = logging.getLogger(__name__)


def _read_key(path: str) -> str | None:
    try:
        p = Path(path)
        if p.is_file():
            key = p.read_text(encoding="utf-8").strip()
            return key or None
    except Exception:
        return None
    return None


class SocietyQuicksilver:
    def __init__(self, config: AgentSocietyConfig) -> None:
        self.config = config
        from .config import CLUTCHBOT_KEY_FILE, DEFAULT_KEY_FILE, resolve_key_file

        self._key = _read_key(config.api_key_file)
        if not self._key and config.api_key_file in {DEFAULT_KEY_FILE, "", None}:
            fallback = resolve_key_file()
            if fallback and fallback != config.api_key_file:
                self._key = _read_key(fallback)
            if not self._key:
                self._key = _read_key(CLUTCHBOT_KEY_FILE)
        if not self._key:
            for env in ("QUICKSILVER_API_KEY", "QUICKSILVERPRO_API_KEY", "QORESENCE_QUICKSILVER_API_KEY"):
                v = os.environ.get(env)
                if v and v.strip():
                    self._key = v.strip()
                    break

    def available(self) -> bool:
        return bool(self._key)

    def complete(self, system: str, user: str, *, model: str) -> str:
        if not self._key:
            return ""
        url = self.config.quicksilver_base.rstrip("/") + "/chat/completions"
        body = json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": 220,
                "temperature": 0.3,
                "stream": False,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
                "User-Agent": "Qoresence-AgentSociety/1.0",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices") or []
            if not choices:
                return ""
            msg = (choices[0].get("message") or {}).get("content") or ""
            return str(msg).strip()
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            log.debug("society Quicksilver failed: %s", e)
            return ""
