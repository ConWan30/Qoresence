"""Operator game-profile pin — last session, env, or explicit CLI.

Auto-detect may still *observe* a title. It must not yank a pin the
operator already chose (or last played). NCAA is only the first-run
fallback when nothing has been pinned yet.
"""

from __future__ import annotations

import os
from pathlib import Path

from qoresence.core.unified_config import GameProfileId, normalize_game_profile

_ENV = "QORESENCE_GAME_PROFILE"
_FALLBACK = GameProfileId.NCAA_FOOTBALL_27.value


def last_profile_path() -> Path:
    override = (os.environ.get("QORESENCE_LAST_PROFILE_PATH") or "").strip()
    if override:
        return Path(override)
    return Path.home() / ".qoresence" / "last_game_profile"


def load_last_profile() -> str | None:
    try:
        raw = last_profile_path().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    try:
        return normalize_game_profile(raw).value
    except ValueError:
        return None


def save_last_profile(profile_id: str | object | None) -> None:
    if profile_id is None:
        return
    try:
        canon = normalize_game_profile(profile_id).value
    except ValueError:
        return
    path = last_profile_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(canon + "\n", encoding="utf-8")
    except OSError:
        return


def resolve_operator_profile(cli_value: str | None = None) -> tuple[str, bool]:
    """Return ``(canonical_id, pinned)``.

    Pinned when CLI, env, or a persisted last-profile exists. First-run
    NCAA fallback is *not* pinned so optics can still lock the live title.
    """
    if cli_value:
        return normalize_game_profile(cli_value).value, True
    env = (os.environ.get(_ENV) or "").strip()
    if env:
        return normalize_game_profile(env).value, True
    last = load_last_profile()
    if last:
        return last, True
    return _FALLBACK, False
