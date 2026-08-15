# NFL roster cache (Madden 27)

Local names for **EA Sports Madden NFL 27**. Public NFL clubs and nflverse
rosters — **not** EA Madden files, ratings, or created players.

## What it does

When `--game-profile madden_27` is on, scorebug / nameplate text is matched
against a local index:

- 32 clubs shipped in `qoresence/profiles/nfl_data/teams.json`
- Optional seasonal roster at `data/nfl/roster.jsonl` (gitignored)

Ambiguous HUD text (`New York`, last name `Brown` with no team/number) is
dropped. ClutchBot only speaks a name that matched.

## Sync rosters (once, then play offline)

```powershell
python scripts/sync_nfl_roster.py --season 2026
```

Source: [nflverse-data](https://github.com/nflverse/nflverse-data) rosters,
**CC-BY 4.0**. Writes `data/nfl/roster.jsonl`.

Without a roster file, **team** matching still works (Chiefs, KC, PHI).
Player nameplates need the JSONL.

## Override path

```powershell
$env:QORESENCE_NFL_ROSTER="D:\rosters\roster.jsonl"
```

## Situation fields (Deck /health)

`home_team`, `away_team`, `home_team_name`, `away_team_name`,
`on_screen_player`, `on_screen_player_team`, `on_screen_player_jersey`

NCAA sessions are unchanged — the matcher is Madden-only.
