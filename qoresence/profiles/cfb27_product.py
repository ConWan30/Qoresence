"""NCAA CFB 27 product rules — one title, this match, observation only.

Keeps the lock on the game being played (not the ticker), treats a locked
scorebug huddle as gameplay so pad phrases can fire, and refuses identity
swaps onto a stranger pair.
"""

from __future__ import annotations

import re
from typing import Any

_PUNCT = re.compile(r"[^A-Z0-9]+")
_MENUISH = frozenset({"menu", "lobby", "hub", "unknown", ""})
_HOLD = frozenset({"replay", "cutscene", "results", "spectating"})
_PAUSE = frozenset({"paused", "pause"})


def _norm(text: Any) -> str:
    return _PUNCT.sub("", str(text or "").upper())


def board_is_live(*, locked: bool, quarter: Any = None, down: Any = None) -> bool:
    if not locked:
        return False
    return quarter is not None or down is not None


def effective_game_state(
    game_state: str | None,
    *,
    locked: bool = False,
    quarter: Any = None,
    down: Any = None,
) -> str:
    """Huddle / play-call often classifies as menu. A live locked board is gameplay."""
    gst = str(game_state or "").strip().lower()
    if gst in _HOLD:
        return gst
    if gst in _PAUSE:
        return "paused"
    if board_is_live(locked=locked, quarter=quarter, down=down) and gst in _MENUISH:
        return "gameplay"
    return gst or "unknown"


def _league(profile: Any) -> str | None:
    p = str(profile or "").lower()
    if "madden" in p or p == "nfl":
        return "nfl"
    if "ncaa" in p or "cfb" in p or "college" in p:
        return "ncaa"
    return None


def _team_keys(name: Any, *, league: str | None = None) -> set[str]:
    """Possible catalog abbrs for a wordmark (sets, so OU and Oklahoma overlap)."""
    raw = _norm(name)
    if not raw:
        return set()
    keys = {raw}
    if league != "nfl":
        try:
            from qoresence.profiles.team_identity import load_teams

            for team in load_teams():
                abbr = _norm(team.abbr)
                names = {_norm(team.name), _norm(team.nick), *(_norm(a) for a in team.aliases), abbr}
                if raw == abbr or raw in names:
                    keys.add(abbr)
                elif len(raw) >= 5 and any(raw in n for n in names if len(n) >= 5):
                    keys.add(abbr)
        except Exception:
            pass
    if league != "ncaa":
        try:
            from qoresence.profiles.nfl_roster import get_nfl_roster

            idx = get_nfl_roster()
            for team in idx.teams.values():
                abbr = _norm(team.abbr)
                names = {_norm(team.name), _norm(team.nick), _norm(team.city), abbr}
                if raw == abbr or raw in names:
                    keys.add(abbr)
                elif len(raw) >= 5 and any(raw in n for n in names if len(n) >= 5):
                    keys.add(abbr)
        except Exception:
            pass
    return keys


def identity_compatible(
    cur_home: Any,
    cur_away: Any,
    new_home: Any,
    new_away: Any,
    *,
    profile: Any = None,
) -> bool:
    """True if new names are empty or share a catalog team with the locked pair."""
    league = _league(profile)
    cur = _team_keys(cur_home, league=league) | _team_keys(cur_away, league=league)
    new = _team_keys(new_home, league=league) | _team_keys(new_away, league=league)
    if not cur or not new:
        return True
    return bool(cur & new)


def vlm_home_away_names(vlm: dict[str, Any] | None) -> tuple[str, str]:
    if not vlm:
        return "", ""
    home_left = bool(vlm.get("home_left"))
    left = str(vlm.get("left_team") or "")
    right = str(vlm.get("right_team") or "")
    if home_left:
        return left, right
    return right, left
