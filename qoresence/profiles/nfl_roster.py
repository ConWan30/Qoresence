"""Local NFL team/player index for Madden 27.

Public names and abbreviations only (nflverse CC-BY 4.0 when synced).
Never invents a team or player. Ambiguous HUD text returns None.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TEAMS_PATH = Path(__file__).resolve().parent / "nfl_data" / "teams.json"
DEFAULT_ROSTER_PATHS = (
    Path("data/nfl/roster.jsonl"),
    Path("data/nfl/roster_2026.jsonl"),
    Path("data/nfl/roster_2025.jsonl"),
)

_PUNCT = re.compile(r"[^A-Z0-9]+")
_NAMEPLATE = re.compile(
    r"(?:(?P<ini>[A-Z])\.\s*)?(?P<last>[A-Z][A-Za-z'\-]{2,})(?:\s+#?(?P<j1>\d{1,2}))?"
    r"|(?:#?(?P<j2>\d{1,2})\s+)(?P<last2>[A-Z][A-Za-z'\-]{2,})",
    re.I,
)


def _norm(text: str | None) -> str:
    if not text:
        return ""
    return _PUNCT.sub("", str(text).upper())


def is_madden_profile(profile: str | object | None) -> bool:
    return "madden" in str(profile or "").lower()


@dataclass(frozen=True)
class NflTeam:
    abbr: str
    city: str
    nick: str
    name: str

    def to_dict(self) -> dict[str, str]:
        return {"abbr": self.abbr, "city": self.city, "nick": self.nick, "name": self.name}


@dataclass(frozen=True)
class NflPlayer:
    full_name: str
    last_name: str
    football_name: str
    jersey: int | None
    position: str
    team: str
    status: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "full_name": self.full_name,
            "last_name": self.last_name,
            "football_name": self.football_name,
            "jersey": self.jersey,
            "position": self.position,
            "team": self.team,
            "status": self.status,
        }


class NflRosterIndex:
    def __init__(self) -> None:
        self.teams: dict[str, NflTeam] = {}
        self._team_keys: dict[str, str] = {}
        self._ambiguous_keys: set[str] = set()
        self.players: list[NflPlayer] = []
        self._by_team_jersey: dict[tuple[str, int], list[NflPlayer]] = {}
        self._by_team_last: dict[tuple[str, str], list[NflPlayer]] = {}
        self.roster_path: Path | None = None

    @classmethod
    def load(
        cls,
        *,
        teams_path: Path | None = None,
        roster_path: Path | str | None = None,
    ) -> NflRosterIndex:
        idx = cls()
        idx._load_teams(Path(teams_path) if teams_path else TEAMS_PATH)
        path = _resolve_roster_path(roster_path)
        if path is not None:
            idx._load_players(path)
            idx.roster_path = path
        return idx

    def _load_teams(self, path: Path) -> None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        for row in raw.get("teams") or []:
            team = NflTeam(
                abbr=str(row["abbr"]).upper(),
                city=str(row.get("city") or ""),
                nick=str(row.get("nick") or ""),
                name=str(row.get("name") or ""),
            )
            self.teams[team.abbr] = team
            keys = {
                _norm(team.abbr),
                _norm(team.city),
                _norm(team.nick),
                _norm(team.name),
                _norm(f"{team.city}{team.nick}"),
            }
            for alias in row.get("aliases") or []:
                keys.add(_norm(alias))
            for key in keys:
                if not key:
                    continue
                prev = self._team_keys.get(key)
                if key in self._ambiguous_keys:
                    continue
                if prev and prev != team.abbr:
                    self._team_keys.pop(key, None)
                    self._ambiguous_keys.add(key)
                else:
                    self._team_keys[key] = team.abbr

    def _load_players(self, path: Path) -> None:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            player = _player_from_row(row)
            if player is None:
                continue
            self.players.append(player)
            if player.jersey is not None:
                self._by_team_jersey.setdefault((player.team, player.jersey), []).append(player)
            if player.last_name:
                self._by_team_last.setdefault((player.team, _norm(player.last_name)), []).append(
                    player
                )

    def match_team(self, text: str | None) -> NflTeam | None:
        key = _norm(text)
        if not key:
            return None
        abbr = self._team_keys.get(key)
        if abbr:
            return self.teams.get(abbr)
        # Unique prefix / contained nick only if one hit
        hits = [t for t in self.teams.values() if key == _norm(t.nick) or key == _norm(t.abbr)]
        if len(hits) == 1:
            return hits[0]
        return None

    def match_player(
        self,
        text: str | None = None,
        *,
        jersey: int | None = None,
        team: str | None = None,
        last_name: str | None = None,
    ) -> NflPlayer | None:
        team_abbr = None
        if team:
            found = self.match_team(team)
            if found:
                team_abbr = found.abbr
            elif _norm(team) in self.teams:
                team_abbr = _norm(team)
        last = _norm(last_name)
        parsed = parse_nameplate(text) if text else {}
        if jersey is None:
            jersey = parsed.get("jersey")
        if not last:
            last = _norm(parsed.get("last"))
        if team_abbr is None and parsed.get("team"):
            tm = self.match_team(str(parsed["team"]))
            team_abbr = tm.abbr if tm else None

        if team_abbr and jersey is not None:
            hits = self._by_team_jersey.get((team_abbr, int(jersey))) or []
            if last:
                hits = [p for p in hits if _norm(p.last_name) == last]
            if len(hits) == 1:
                return hits[0]
            return None
        if team_abbr and last:
            hits = self._by_team_last.get((team_abbr, last)) or []
            if len(hits) == 1:
                return hits[0]
            return None
        return None

    def resolve(
        self,
        *,
        home_raw: str | None = None,
        away_raw: str | None = None,
        possession: str | None = None,
        nameplate: str | None = None,
        jersey: int | None = None,
    ) -> dict[str, Any]:
        home = self.match_team(home_raw)
        away = self.match_team(away_raw)
        poss_team = None
        poss_n = (possession or "").strip().lower()
        if poss_n in {"home", "h"} and home:
            poss_team = home
        elif poss_n in {"away", "a"} and away:
            poss_team = away
        else:
            poss_team = self.match_team(possession)

        side = None
        if poss_team and home and poss_team.abbr == home.abbr:
            side = "home"
        elif poss_team and away and poss_team.abbr == away.abbr:
            side = "away"

        team_hint = poss_team.abbr if poss_team else None
        player = self.match_player(nameplate, jersey=jersey, team=team_hint)
        if player is None and home:
            player = self.match_player(nameplate, jersey=jersey, team=home.abbr)
        if player is None and away:
            player = self.match_player(nameplate, jersey=jersey, team=away.abbr)

        out: dict[str, Any] = {
            "home_team": home.to_dict() if home else None,
            "away_team": away.to_dict() if away else None,
            "possession_team": poss_team.to_dict() if poss_team else None,
            "possession_side": side,
            "on_screen_player": player.to_dict() if player else None,
        }
        return out


_index: NflRosterIndex | None = None


def get_nfl_roster(*, reload: bool = False) -> NflRosterIndex:
    global _index
    if _index is None or reload:
        _index = NflRosterIndex.load()
    return _index


def parse_nameplate(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    m = _NAMEPLATE.search(text.strip())
    if not m:
        return {}
    last = m.group("last") or m.group("last2")
    jersey = m.group("j1") or m.group("j2")
    out: dict[str, Any] = {}
    if last:
        out["last"] = last
    if jersey:
        try:
            out["jersey"] = int(jersey)
        except ValueError:
            pass
    return out


def apply_roster_to_context(ctx: Any, parsed: dict[str, Any] | None = None) -> Any:
    """Fill resolved Madden team/player fields. No-op unless profile is Madden."""
    parsed = parsed or {}
    profile = getattr(ctx, "game_profile", None) or parsed.get("game_profile")
    if not is_madden_profile(profile):
        return ctx
    idx = get_nfl_roster()
    home_raw = parsed.get("home_team_raw") or getattr(ctx, "home_team_raw", None)
    away_raw = parsed.get("away_team_raw") or getattr(ctx, "away_team_raw", None)
    nameplate = parsed.get("player_name") or getattr(ctx, "player_name_raw", None)
    jersey = parsed.get("player_jersey")
    if jersey is None:
        jersey = getattr(ctx, "player_jersey", None)
    resolved = idx.resolve(
        home_raw=home_raw,
        away_raw=away_raw,
        possession=getattr(ctx, "possession", None),
        nameplate=nameplate,
        jersey=int(jersey) if jersey is not None else None,
    )
    if home_raw:
        ctx.home_team_raw = str(home_raw)
    if away_raw:
        ctx.away_team_raw = str(away_raw)
    home = resolved.get("home_team")
    away = resolved.get("away_team")
    if home:
        ctx.home_team = home["abbr"]
        ctx.home_team_name = home["name"]
    if away:
        ctx.away_team = away["abbr"]
        ctx.away_team_name = away["name"]
    player = resolved.get("on_screen_player")
    if player:
        ctx.on_screen_player = player["full_name"]
        ctx.on_screen_player_team = player["team"]
        ctx.on_screen_player_jersey = player.get("jersey")
        ctx.on_screen_player_pos = player.get("position")
    return ctx


def _resolve_roster_path(explicit: Path | str | None) -> Path | None:
    env = os.environ.get("QORESENCE_NFL_ROSTER")
    for cand in (explicit, env, *DEFAULT_ROSTER_PATHS):
        if not cand:
            continue
        p = Path(cand)
        if p.is_file():
            return p
    return None


def _player_from_row(row: dict[str, Any]) -> NflPlayer | None:
    full = str(row.get("full_name") or row.get("player_name") or "").strip()
    last = str(row.get("last_name") or "").strip()
    if not last and full:
        last = full.split()[-1]
    if not full and not last:
        return None
    team = str(row.get("team") or row.get("team_abbr") or "").upper().strip()
    if not team:
        return None
    jersey = row.get("jersey_number", row.get("jersey"))
    try:
        jersey_i = int(jersey) if jersey not in (None, "", "NA") else None
    except (TypeError, ValueError):
        jersey_i = None
    return NflPlayer(
        full_name=full or last,
        last_name=last,
        football_name=str(row.get("football_name") or full or last),
        jersey=jersey_i,
        position=str(row.get("position") or ""),
        team=team,
        status=str(row.get("status") or ""),
    )
