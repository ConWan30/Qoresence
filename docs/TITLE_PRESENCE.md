# Optical title-presence (observation only)

Hardens `GameAutoDetector` with a hysteresis FSM and a hard `plane` tag.  
**On with `--play` / `--stream`.** Opt out with `--no-title-presence` (or `--no-game-detect` to stop the detector entirely).

## Enable

```powershell
python -m qoresence.cli --play --deck --monitor --controller --streamer-device 0 --game-profile madden_27
```

Title-presence starts with that stack. An explicit `--game-profile` is pinned: a locked optical title is observed but will not yank the operator profile.

## What you get

- Event `title_presence` on state changes (`unknown` / `transitioning` / `overlay-rejected` / `locked`).
- `game_detected` only when **locked** (claim=true). Payload includes `plane: "qoresence-observation"` and nested `title_presence`.
- Frames from FrameHub `get_latest` first, then the streamer buffer. Never a second capture card.
- No scores, names, humanity, or eligibility in the record.

## Read a record

`claim==false` → `profile_id` is null (`no_claim_reason` set). Prefer no claim over an unstable title.

## Feature OFF

Incumbent `game_detected` timing is unchanged (no plane, no `title_presence` events).

## Lock-and-verify (still sparse)

Raised poll (~1 s) for ~6 s on: first visual, operator profile hint, menu→gameplay, first score lock, SNAP/SPRINT phrase, fused title flip. Never 60 Hz.

## Re-wrap ceremony

`qoresence.vision.title_presence_wrap.wrap_observation_for_plane` is fail-closed. Default dest allowlist is empty. It never mutates the observation record and never writes a truth-plane store.

## Research sidecar

When `--title-presence` **and** local learning are both on, a JSONL sidecar `title_presence_ingredients.jsonl` links `source_hash` + decay. The optical record is not rewritten.
