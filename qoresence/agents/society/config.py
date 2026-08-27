"""Agent Society config — default OFF, rules-only if key missing."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .types import KNOWN_ROLES

DEFAULT_BASE = "https://api.quicksilverpro.io/v1"
# Phrasing/reason/scene = DeepSeek V4 Flash (text-only, cheap)
DEFAULT_REASON = "deepseek-v4-flash"
DEFAULT_SCENE = "deepseek-v4-flash"
DEFAULT_KEY_FILE = ".secrets/quicksilver.key"
CLUTCHBOT_KEY_FILE = ".secrets/quicksilver_clutchbot.key"


def resolve_key_file(explicit: str | None = None) -> str:
    """Prefer an explicit path, then society file, then ClutchBot's key."""
    if explicit and Path(explicit).is_file():
        return explicit
    env = os.environ.get("QORESENCE_SOCIETY_KEY_FILE") or os.environ.get(
        "QORESENCE_QUICKSILVER_KEY_FILE"
    )
    if env and Path(env).is_file():
        return env
    for cand in (DEFAULT_KEY_FILE, CLUTCHBOT_KEY_FILE):
        if Path(cand).is_file():
            return cand
    return explicit or env or DEFAULT_KEY_FILE


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _csv_roles(raw: str | None) -> tuple[str, ...]:
    """Personality roles are deleted. Unknown names are ignored."""
    if not raw or not raw.strip():
        return ()
    out: list[str] = []
    for part in raw.split(","):
        r = part.strip().lower()
        if r in KNOWN_ROLES and r not in out:
            out.append(r)
    return tuple(out)


@dataclass(frozen=True)
class AgentSocietyConfig:
    enabled: bool = False
    roles: tuple[str, ...] = ()
    quicksilver_base: str = DEFAULT_BASE
    api_key_file: str = DEFAULT_KEY_FILE
    model_reason: str = DEFAULT_REASON
    model_scene: str = DEFAULT_SCENE
    max_calls_per_hour: int = 30
    cooldown_s: float = 45.0
    allow_frame: bool = False
    mirror_timeline: bool = True

    def has_key_file(self) -> bool:
        return Path(self.api_key_file).is_file()

    @classmethod
    def from_env(cls) -> AgentSocietyConfig:
        key = resolve_key_file()
        return cls(
            enabled=_bool("QORESENCE_AGENT_SOCIETY"),
            roles=_csv_roles(os.environ.get("QORESENCE_AGENT_SOCIETY_ROLES")),
            quicksilver_base=(
                os.environ.get("QORESENCE_QUICKSILVER_BASE")
                or os.environ.get("QORESENCE_CLUTCHBOT_LLM_BASE_URL")
                or DEFAULT_BASE
            ).rstrip("/"),
            api_key_file=key or DEFAULT_KEY_FILE,
            model_reason=os.environ.get("QORESENCE_SOCIETY_MODEL_REASON") or DEFAULT_REASON,
            model_scene=os.environ.get("QORESENCE_SOCIETY_MODEL_SCENE") or DEFAULT_SCENE,
            max_calls_per_hour=int(os.environ.get("QORESENCE_SOCIETY_MAX_CALLS_PER_HOUR") or 30),
            cooldown_s=float(os.environ.get("QORESENCE_SOCIETY_COOLDOWN_S") or 45),
            allow_frame=_bool("QORESENCE_SOCIETY_ALLOW_FRAME", False),
            mirror_timeline=_bool("QORESENCE_SOCIETY_MIRROR_TIMELINE", True),
        )
