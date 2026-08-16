"""Bind scorebug name + jersey color + logo to the score on that side.

Observation only. A side's color and logo never travel with the other
side's score. Catalog is public school colors/mascots, not EA data.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_TEAMS_PATH = Path(__file__).resolve().parent / "ncaa_teams.json"
_PUNCT = re.compile(r"[^A-Z0-9]+")


def _norm(text: str | None) -> str:
    return _PUNCT.sub("", str(text or "").upper())


def _tokens(text: str | None) -> set[str]:
    raw = re.findall(r"[a-z0-9]+", str(text or "").lower())
    return {t for t in raw if len(t) > 1}


@dataclass(frozen=True)
class TeamLook:
    abbr: str
    name: str
    nick: str
    aliases: tuple[str, ...]
    colors: tuple[str, ...]
    primary: str
    logo: tuple[str, ...]
    hex: str

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(
            k
            for k in (_norm(self.abbr), _norm(self.name), _norm(self.nick), *(_norm(a) for a in self.aliases))
            if k
        )


_CACHE: tuple[TeamLook, ...] | None = None


def load_teams() -> tuple[TeamLook, ...]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    data = json.loads(_TEAMS_PATH.read_text(encoding="utf-8"))
    out: list[TeamLook] = []
    for row in data.get("teams") or []:
        out.append(
            TeamLook(
                abbr=str(row["abbr"]),
                name=str(row["name"]),
                nick=str(row.get("nick") or ""),
                aliases=tuple(str(a) for a in (row.get("aliases") or [])),
                colors=tuple(str(c).lower() for c in (row.get("colors") or [])),
                primary=str(row.get("primary") or (row.get("colors") or ["gray"])[0]).lower(),
                logo=tuple(str(x).lower() for x in (row.get("logo") or [])),
                hex=str(row.get("hex") or ""),
            )
        )
    _CACHE = tuple(out)
    return _CACHE


def _name_hit(team: TeamLook, name_n: str) -> bool:
    if not name_n:
        return False
    return any(name_n == k or (len(k) >= 3 and (name_n in k or k in name_n)) for k in team.keys)


def _logo_hit(team: TeamLook, logo_t: set[str]) -> bool:
    if not logo_t:
        return False
    marks = set()
    for piece in team.logo:
        marks.update(_tokens(piece))
        marks.add(_norm(piece).lower())
    return bool(logo_t & marks)


def match_team(
    *,
    name: str | None = None,
    color: str | None = None,
    logo: str | None = None,
) -> TeamLook | None:
    """Logo+color on a scorebug side beat a swapped wordmark."""
    name_n = _norm(name)
    color_t = _tokens(color)
    logo_t = _tokens(logo)
    logo_teams = [t for t in load_teams() if _logo_hit(t, logo_t)]
    name_teams = [t for t in load_teams() if _name_hit(t, name_n)]
    color_ok = lambda t: bool(color_t and any(c in color_t for c in t.colors))

    if len(logo_teams) == 1:
        vis = logo_teams[0]
        if not name_teams or vis in name_teams or color_ok(vis) or not color_t:
            return vis
    if len(name_teams) == 1:
        return name_teams[0]
    scored: list[tuple[int, TeamLook]] = []
    for team in load_teams():
        s = 0
        if team in name_teams:
            s += 3
        if team in logo_teams:
            s += 4
        if color_ok(team):
            s += 1
        if s:
            scored.append((s, team))
    if not scored:
        return None
    scored.sort(key=lambda r: r[0], reverse=True)
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    return scored[0][1] if scored[0][0] >= 2 else None


def _side_identity(name: str | None, color: str | None, logo: str | None) -> dict[str, str]:
    hit = match_team(name=name, color=color, logo=logo)
    if hit is None and name:
        hit = match_team(name=name)
    color_out = (color or "").strip().lower() or (hit.primary if hit else "")
    logo_out = (logo or "").strip().lower() or (hit.logo[0] if hit and hit.logo else "")
    if hit is not None:
        return {
            "team": hit.abbr,
            "team_name": hit.name,
            "color": color_out or hit.primary,
            "logo": logo_out or (hit.logo[0] if hit.logo else ""),
            "hex": hit.hex,
        }
    raw = (name or "").strip()
    return {
        "team": _norm(raw)[:8] or "",
        "team_name": raw,
        "color": color_out,
        "logo": logo_out,
        "hex": "",
    }


def bind_scoreboard_sides(
    *,
    left_name: str | None,
    left_color: str | None,
    left_logo: str | None,
    left_score: int | None,
    right_name: str | None,
    right_color: str | None,
    right_logo: str | None,
    right_score: int | None,
    home_left: bool = False,
) -> dict[str, Any]:
    """Glue each side's name/color/logo to that side's score, then label home/away."""
    left = _side_identity(left_name, left_color, left_logo)
    right = _side_identity(right_name, right_color, right_logo)
    if home_left:
        home, away = left, right
        hs, aws = left_score, right_score
    else:
        home, away = right, left
        hs, aws = right_score, left_score
    return {
        "home_team": home["team"] or None,
        "home_team_name": home["team_name"] or None,
        "home_color": home["color"] or None,
        "home_logo": home["logo"] or None,
        "home_hex": home["hex"] or None,
        "home_score": left_score if home_left else right_score,
        "away_team": away["team"] or None,
        "away_team_name": away["team_name"] or None,
        "away_color": away["color"] or None,
        "away_logo": away["logo"] or None,
        "away_hex": away["hex"] or None,
        "away_score": right_score if home_left else left_score,
        "home_left": bool(home_left),
        "_check_home_score": hs,
        "_check_away_score": aws,
    }


def apply_identity_to_context(ctx: Any, parsed: dict[str, Any]) -> None:
    """Write bound identity onto VisualContext. Safe no-op if fields missing."""
    try:
        from qoresence.profiles.nfl_roster import is_madden_profile

        if is_madden_profile(getattr(ctx, "game_profile", None) or parsed.get("game_profile")):
            return
    except Exception:
        pass
    left_name = parsed.get("left_team") or (
        parsed.get("home_team_raw") if parsed.get("home_left") else parsed.get("away_team_raw")
    )
    right_name = parsed.get("right_team") or (
        parsed.get("away_team_raw") if parsed.get("home_left") else parsed.get("home_team_raw")
    )
    if not any(
        (
            left_name,
            right_name,
            parsed.get("left_color"),
            parsed.get("left_logo"),
            parsed.get("right_color"),
            parsed.get("right_logo"),
        )
    ):
        return
    home_left = bool(parsed.get("home_left")) if parsed.get("home_left") is not None else bool(
        getattr(ctx, "home_left", False)
    )
    bound = bind_scoreboard_sides(
        left_name=left_name,
        left_color=parsed.get("left_color"),
        left_logo=parsed.get("left_logo"),
        left_score=parsed.get("left_score", parsed.get("away_score") if not home_left else parsed.get("home_score")),
        right_name=right_name,
        right_color=parsed.get("right_color"),
        right_logo=parsed.get("right_logo"),
        right_score=parsed.get("right_score", parsed.get("home_score") if not home_left else parsed.get("away_score")),
        home_left=home_left,
    )
    ctx.home_team = bound["home_team"] or ctx.home_team
    ctx.home_team_name = bound["home_team_name"] or ctx.home_team_name
    ctx.away_team = bound["away_team"] or ctx.away_team
    ctx.away_team_name = bound["away_team_name"] or ctx.away_team_name
    ctx.home_color = bound["home_color"]
    ctx.home_logo = bound["home_logo"]
    ctx.away_color = bound["away_color"]
    ctx.away_logo = bound["away_logo"]
    if bound.get("home_hex"):
        ctx.home_hex = bound["home_hex"]
    if bound.get("away_hex"):
        ctx.away_hex = bound["away_hex"]
    if bound["home_score"] is not None:
        ctx.home_score = bound["home_score"]
    if bound["away_score"] is not None:
        ctx.away_score = bound["away_score"]
    ctx.home_left = home_left
