# Astra Slice C — Football game observation adapter

**Status:** implemented (v0). Default OFF — does not change `QORESENCE_OBSERVATIONS`.

## Goal

Keep the observation reducer generic. Football phases, HUD regions, moment
boundaries, outcome rules (none yet), valid transitions, and known blind spots
live in `qoresence/observation/adapters/football/`.

## Enable

```powershell
# Explicit adapter path (normalize + reducer policy)
$env:QORESENCE_FOOTBALL_ADAPTER="1"

# Or auto-select when the observations runtime is already on (default still OFF):
$env:QORESENCE_OBSERVATIONS="1"
```

Non-football `game_category` values always abstain — no invented football moments.

## Protocol

`GameObservationAdapter` (`adapters/protocol.py`) defines:

- `visual_phases`, `active_phases`, `boundary_phases`, `boundary_game_states`
- `hud_regions(profile)`, `blind_spots(profile)`, `valid_transitions()`
- `should_open_moment` / `should_close_moment`
- `normalize_visual`, `qualified_claim`, `new_candidate_record`
- `input_availability(hid_observed=…)` — never invent DualSense presses

## FootballAdapter v0

Shared across CFB and Madden:

- **Active (open):** running, passing, ball_in_air, coverage, defense_pursuit,
  defense_engaged, blocking, player_locked_receiver
- **Boundary (close):** huddle_offense, huddle_defense; game_state replay /
  results / menu / paused
- **Preplay only:** snap does not open a candidate interval
- **Timeout:** 30s open interval → unresolved

Profile honesty (`profiles.py`):

| Profile family | Extra blind spots |
|----------------|-------------------|
| `cfb_27` / NCAA | scorebug huddle→menu without title-presence lock; CFB sheet naming |
| `madden_27` | challenge/overtime UI outside allowlist; NFL abbrev gate |

## Input availability

DualSense stays on the PS5 (Path B). Without a separately observed HID join on
this host, `input_availability` is `not_on_this_host`. Never upgraded to
`available` unless `hid_observed=True` at the adapter call site.

## Tests

```powershell
python -m pytest tests/test_observation_football_adapter.py tests/test_observation_lifecycle.py tests/test_observation_event_replay.py -q
```

Draft only. Do not merge without operator GO MERGE.
