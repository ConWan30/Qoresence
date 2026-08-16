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

## Re-wrap ceremony (live, fail-closed)

`wrap_observation_for_plane` and `run_research_ceremony` are live. Default dest allowlist is **`qoresence-research` only**. `qortroller-truth` (and any dest containing `qortroller` / `poac` / ending in `-truth`) is denied even if passed in an allowlist.

Requires an operator grant (`QORESENCE_WRAP_GRANT_ID`, optional dest/expiry/token). Missing or expired grant → refuse. The optical record is never mutated; the envelope points at `source_hash`.

Live path:

- MCP `wrap_observation` — wraps the last bus `title_presence` claim (no file write)
- Auto-wrap on lock when the grant env is set; sidecar `title_presence_wraps.jsonl` if local learning is on

## Research sidecar + ceremony

When title-presence **and** local learning are both on, `title_presence_ingredients.jsonl` links `source_hash` + decay. The ceremony path (`run_research_ceremony`) attaches the same `source_hash` to the research wrap. The optical record is not rewritten.
