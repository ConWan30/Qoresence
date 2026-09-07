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

# Consumed by save_last_profile when CLI still calls it after resolve.
# False → no-op (unpinned NCAA fallback must not create last_game_profile).
# True/None → write as usual. Cleared on every save_last_profile call.
_last_resolve_pinned: bool | None = None


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
    """Persist last profile; no-op when the prior resolve was unpinned.

    Legacy CLI calls ``save_last_profile`` after ``resolve_operator_profile``.
    Prefer ``persist_operator_pin(..., pinned=)`` at new call sites.
    """
    global _last_resolve_pinned
    pinned_gate = _last_resolve_pinned
    _last_resolve_pinned = None
    if pinned_gate is False:
        return
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


def persist_operator_pin(profile_id: str | object | None, *, pinned: bool) -> None:
    """Write ``last_game_profile`` only for an actual pin (CLI / env / last).

    Unpinned first-run NCAA fallback must not create the file — otherwise the
    next resolve (and the switch-callback last-file safety net) treats NCAA
    as pinned and optics cannot lock the live title.
    """
    global _last_resolve_pinned
    if not pinned:
        return
    # Bypass resolve→save gate so an explicit pin always writes.
    _last_resolve_pinned = None
    save_last_profile(profile_id)


def _canonical_profile_id(profile_id: str | object | None) -> str | None:
    if profile_id is None:
        return None
    try:
        return normalize_game_profile(profile_id).value
    except ValueError:
        raw = getattr(profile_id, "value", None)
        text = str(raw if raw is not None else profile_id).strip()
        return text or None


def operator_pin_blocks_switch(
    operator_profile: str | object | None,
    optical_profile: str | object | None,
    *,
    pinned: bool,
) -> bool:
    """True when optics must not overwrite the operator profile.

    Last-session file is a pin only when it matches the resolved operator
    id (belt if ``game_profile_pinned`` was not copied onto config). An
    unpinned NCAA fallback is not persisted, so it cannot self-pin.
    """
    want = _canonical_profile_id(operator_profile)
    got = _canonical_profile_id(optical_profile)
    if want is None or got is None:
        return bool(pinned)
    if not pinned:
        last = load_last_profile()
        pinned = bool(last) and last == want
    return bool(pinned) and want != got


def resolve_operator_profile(cli_value: str | None = None) -> tuple[str, bool]:
    """Return ``(canonical_id, pinned)``.

    Pinned when CLI, env, or a persisted last-profile exists. First-run
    NCAA fallback is *not* pinned so optics can still lock the live title.
    """
    global _last_resolve_pinned
    if cli_value:
        pid, pinned = normalize_game_profile(cli_value).value, True
    else:
        env = (os.environ.get(_ENV) or "").strip()
        if env:
            pid, pinned = normalize_game_profile(env).value, True
        else:
            last = load_last_profile()
            if last:
                pid, pinned = last, True
            else:
                pid, pinned = _FALLBACK, False
    _last_resolve_pinned = pinned
    return pid, pinned
