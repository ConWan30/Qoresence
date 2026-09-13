"""Fail-closed board speech — why the seeing path did or did not mint.

Observation only. Never a last-good score. Never button names. Do not put
operator ``why_strip`` / ``confirm: none`` on the gamer Now strip.
"""

from __future__ import annotations

from typing import Any

# Licensed
BOARD_WHY_LICENSED = "confirm_ticket"

# Unlocked speech (stable for tests)
BOARD_WHY_UNLOCKED = frozenset(
    {
        "unlocked",
        "no_ticket",
        "menu",
        "loading",
        "vlm_none",
        "vlm_ungrounded",
        "vlm_quota",
        "vlm_auth",
        "vlm_no_key",
        "refuse_zero_zero",
        "refuse_identity_swap",
        "refuse_suspicious",
    }
)

BOARD_WHY_VALUES = frozenset({BOARD_WHY_LICENSED}) | BOARD_WHY_UNLOCKED

VLM_STATUSES = frozenset(
    {
        "ok",
        "ungrounded",
        "http_400",
        "http_401",
        "http_402",
        "http_429",
        "no_key",
        "stale",
        "none",
    }
)

# garbage_lock_reason tokens → board_why
_REFUSE_TO_WHY = {
    "suspicious_pair": "refuse_suspicious",
    "zero_zero_after_identity_swap": "refuse_zero_zero",
    "zero_zero_after_nonzero": "refuse_zero_zero",
    "zero_zero_kickoff": "refuse_zero_zero",
    "empty_crop_hash": "vlm_ungrounded",
    "identity_swap": "refuse_identity_swap",
    "zero_zero_menu": "menu",
    "player_cu_crop": "vlm_ungrounded",
    "no_scorebug_sides": "vlm_ungrounded",
    "empty_crop": "vlm_ungrounded",
    "tiny_crop": "vlm_ungrounded",
    "vlm_ungrounded": "vlm_ungrounded",
}

_LOADING_STATES = frozenset({"loading", "cutscene", "intro", "replay"})
_MENU_STATES = frozenset({"menu", "paused", "lobby", "results", "spectating", "hub", "pause"})

# Gamer Now strip — one sentence each. Not operator why_strip.
BOARD_WHY_SPEECH = {
    "confirm_ticket": "",
    "unlocked": "Board not licensed yet",
    "no_ticket": "Board not licensed yet",
    "menu": "Menu — board not licensed",
    "loading": "Loading — board not licensed",
    "vlm_none": "Board unread",
    "vlm_ungrounded": "Board unread",
    "vlm_quota": "Board unread (quota)",
    "vlm_auth": "Board unread (auth)",
    "vlm_no_key": "Board unread (no key)",
    "refuse_zero_zero": "Board not licensed yet",
    "refuse_identity_swap": "Board not licensed yet",
    "refuse_suspicious": "Board not licensed yet",
}


def normalize_board_why(value: Any, *, default: str = "unlocked") -> str:
    token = str(value or "").strip()
    if token in BOARD_WHY_VALUES:
        return token
    return default if default in BOARD_WHY_VALUES else "unlocked"


def normalize_vlm_status(value: Any) -> str:
    token = str(value or "").strip()
    if token in VLM_STATUSES:
        return token
    return "none"


_PREPLAY_VC_PROMPTS = frozenset(
    {"preplay", "subs", "snap", "flip", "flip play", "audible", "select play"}
)


def vlm_has_scorebug_wordmarks(last: dict[str, Any] | None) -> bool:
    """True when left/right wordmarks (or licensed NFL tags) are on the parse."""
    if not last:
        return False
    left = str(last.get("left_team") or "").strip()
    right = str(last.get("right_team") or "").strip()
    if left and right:
        return True
    try:
        from qoresence.profiles.nfl_roster import licensed_nfl_abbr

        tags: list[str] = []
        for key in ("left_team", "right_team", "home_team", "away_team"):
            token = str(last.get(key) or "").strip().upper()
            if token and licensed_nfl_abbr(token):
                tags.append(token)
        return len(set(tags)) >= 2
    except Exception:
        return False


def vlm_looks_like_live_ingame_hud(last: dict[str, Any] | None) -> bool:
    """Down+distance+quarter+scores — preplay stick HUD, not SELECT pause plate."""
    if not last:
        return False
    if last.get("home_score") is None or last.get("away_score") is None:
        return False
    if last.get("quarter") is None or last.get("down") is None:
        return False
    if last.get("yards_to_go") is None:
        return False
    return True


def normalize_vlm_paused_flag(last: dict[str, Any] | None) -> dict[str, Any] | None:
    """Preplay Subs/Preplay stick HUD is gameplay — not true pause/SELECT."""
    if not last or not last.get("paused"):
        return last
    vc = last.get("visible_control") if isinstance(last.get("visible_control"), dict) else {}
    prompt = str(vc.get("prompt") or "").strip().lower()
    if prompt in _PREPLAY_VC_PROMPTS or "preplay" in prompt or prompt == "subs":
        return {**last, "paused": False}
    # Wordmarks only — down+distance without teams is still honest paused=true
    # (e.g. SELECT 20-0 plate); preplay clears via visible_control prompt above.
    if vlm_has_scorebug_wordmarks(last):
        return {**last, "paused": False}
    return last


def vlm_last_grounded(last: dict[str, Any] | None) -> bool:
    """True when the last VLM JSON looks like this match's scorebug, not a lone pair."""
    if not last:
        return False
    last = normalize_vlm_paused_flag(dict(last)) or last
    if last.get("home_score") is None or last.get("away_score") is None:
        return False
    # Pause / SELECT plates invent 12-15 with clock+quarter but no wordmarks.
    if last.get("paused") and not vlm_has_scorebug_wordmarks(last):
        return False
    if vlm_has_scorebug_wordmarks(last):
        return True
    left = str(last.get("left_team") or "").strip()
    right = str(last.get("right_team") or "").strip()
    if left and right:
        return True
    clock = last.get("clock_seconds")
    if clock is None:
        return False
    try:
        int(clock)
    except (TypeError, ValueError):
        return False
    return last.get("quarter") is not None or last.get("down") is not None


def classify_vlm_status(
    *,
    has_key: bool,
    http_status: int | None = None,
    last: dict[str, Any] | None = None,
    age_s: float | None = None,
    stale_after_s: float = 15.0,
    grounded: bool | None = None,
) -> str:
    """Classify a VLM outcome. Never includes response bodies."""
    if not has_key:
        return "no_key"
    if http_status == 400:
        return "http_400"
    if http_status == 401:
        return "http_401"
    if http_status == 402:
        return "http_402"
    if http_status == 429:
        return "http_429"
    if last is None:
        return "none"
    if age_s is not None and age_s > stale_after_s:
        return "stale"
    if grounded is False:
        return "ungrounded"
    if grounded is True:
        return "ok"
    if last.get("home_score") is None or last.get("away_score") is None:
        return "ungrounded"
    return "ok"


def vlm_status_to_board_why(status: Any) -> str:
    st = normalize_vlm_status(status)
    if st in {"http_401"}:
        return "vlm_auth"
    if st in {"http_400"}:
        return "vlm_none"
    if st in {"http_402", "http_429"}:
        return "vlm_quota"
    if st == "no_key":
        return "vlm_no_key"
    if st == "ungrounded":
        return "vlm_ungrounded"
    if st in {"none", "stale"}:
        return "vlm_none"
    return "unlocked"


def refuse_to_board_why(refuse: str | None, game_state: str = "") -> str:
    if not refuse:
        return "unlocked"
    token = str(refuse).strip()
    if token == "game_state":
        gst = str(game_state or "").lower()
        if gst in _MENU_STATES:
            return "menu"
        return "loading"
    if token in _LOADING_STATES:
        return "loading"
    if token in _MENU_STATES:
        return "menu"
    mapped = _REFUSE_TO_WHY.get(token)
    if mapped:
        return mapped
    if token in BOARD_WHY_VALUES:
        return token
    return "unlocked"


def infer_board_why(
    *,
    minted: bool = False,
    confirm_ticket_id: str = "",
    score_vlm_locked: bool = False,
    refuse: str | None = None,
    vlm_status: str = "none",
    game_state: str = "",
) -> str:
    """Pick one canonical why for this tick. Fail-closed; no last-good score."""
    tid = str(confirm_ticket_id or "").strip()
    if minted and tid:
        return BOARD_WHY_LICENSED
    if score_vlm_locked and not tid:
        return "no_ticket"
    if refuse:
        return refuse_to_board_why(refuse, game_state)
    gst = str(game_state or "").lower()
    if gst in _LOADING_STATES:
        return "loading"
    if gst in _MENU_STATES:
        return "menu"
    st = normalize_vlm_status(vlm_status)
    if st != "ok":
        return vlm_status_to_board_why(st)
    return "unlocked"


def gamer_board_speech(why: Any) -> str:
    token = normalize_board_why(why)
    return BOARD_WHY_SPEECH.get(token) or "Board not licensed yet"
