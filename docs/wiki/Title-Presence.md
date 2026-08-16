# Title presence

Optical title lock around `GameAutoDetector`. Observation plane only (`plane: "qoresence-observation"`).

**On with `--play` / `--stream`.** Opt out: `--no-title-presence` or `--no-game-detect`.

- States: `unknown` → `transitioning` → `overlay-rejected` | `locked`
- Only **locked** emits `game_detected` with a claim
- Pause/menu/hub is no-claim; a huddle with a locked scorebug still counts as gameplay
- An explicit `--game-profile` is **pinned** — optics will not yank it
- No scores or player names in the title record

Full doc: [docs/TITLE_PRESENCE.md](https://github.com/ConWan30/Qoresence/blob/main/docs/TITLE_PRESENCE.md)
