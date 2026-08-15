# Community Game-Profile SDK

Define custom game profiles via YAML — no Python code changes needed.

## Quick start

1. Create a YAML file in `profiles/`:

```yaml
# profiles/my_game.yaml
profile_id: my_game
display_name: My Game
category: other          # "football" | "shooter" | "other"
event_types:
  - match_start
  - match_end
  - score
  - level_up
outcome_fields:
  - score
  - level
  - player_name
aliases:
  - mg
  - mygame
```

2. Start Qoresence — the profile is auto-loaded:

```
python -m qoresence.cli --profiles-list
```

Output:
```
ID                        Name                                 Cat        Ev   Fld  Type
------------------------------------------------------------------------------------------
ncaa_football_27          NCAA College Football 27             football   16   9    built-in
madden_27                 EA Sports Madden NFL 27              football   18   9    built-in
call_of_duty              Call of Duty (Warzone / Multiplayer) shooter    10   8    built-in
valorant                  Valorant                             shooter    13   10   built-in
apex_legends              Apex Legends                         shooter    13   10   built-in
fortnite                  Fortnite                             shooter    12   9    built-in
my_game                   My Game                              other      4    3    community
```

3. Use the profile:

```
python -m qoresence.cli --play --game-profile my_game
```

## YAML schema

| Field           | Required | Type         | Description                                      |
|-----------------|----------|--------------|--------------------------------------------------|
| `profile_id`    | yes      | string       | Unique identifier (used in `--game-profile`)     |
| `display_name`  | no       | string       | Human-readable name (defaults to `profile_id`)   |
| `category`      | no       | string       | `"football"`, `"shooter"`, or `"other"`           |
| `event_types`   | yes      | list[string] | Event names this game can emit (at least 1)      |
| `outcome_fields`| no       | list[string] | Fields that appear in outcome events             |
| `aliases`       | no       | list[string] | Alternative names for CLI/VLM normalization      |

## Python API

```python
from qoresence.profiles.sdk import load_community_profiles, list_profiles

# Load all YAML profiles from profiles/ (or a custom path)
count = load_community_profiles()
print(f"Loaded {count} community profiles")

# List all registered profiles (built-in + community)
for p in list_profiles():
    print(f"{p['profile_id']}: {p['display_name']} ({p['category']})")
```

## How it works

- At CLI startup, `load_community_profiles()` scans `profiles/*.y*ml`
- Each valid YAML file is parsed into a `GameProfile` and added to
  `GAME_PROFILE_REGISTRY`
- Aliases are added to `GAME_PROFILE_ALIASES` for CLI/VLM normalization
- Community profiles are marked with `community=True` in `list_profiles()`
- Built-in profiles (NCAA, Madden 27, CoD, Valorant, Apex, Fortnite) are always
  available and cannot be overridden by community profiles

## Example: Rocket League

See `profiles/rocket_league.yaml` for a complete example with goals,
saves, assists, demos, and overtime events.

## Limitations

- Community profiles share the `_process_shooter` or `_process_football`
  outcome detection logic based on their `category`. Custom event
  detection logic (e.g., detecting a "goal" in Rocket League) requires
  Python code — the YAML schema defines the vocabulary, not the
  detection rules.
- The VLM (visual language model) needs to be trained or prompted to
  recognize the game's scoreboard layout. Community profiles work best
  with games that have standard scoreboard formats (scores, timers,
  kill counters).
